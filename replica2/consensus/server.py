import os
from typing import Any

from fastapi import FastAPI
from pydantic import BaseModel

from .node import RaftNode
from .state import NodeState
from shared.logger import ElectionLogger
from replica.log.logStore import LogStore
from replica.log.commitManager import CommitManager
from replica.log.appendEntries import handle_append_entries
from replica.log.undoManager import UndoManager
from replica.log.models import EntryType

app = FastAPI(title="Mini-RAFT Consensus Server")

NODE_ID = os.getenv("NODE_ID", "1")
PEERS = [peer.strip() for peer in os.getenv("PEERS", "").split(",") if peer.strip()]

logger = ElectionLogger(NODE_ID)
node = RaftNode(NODE_ID, PEERS, logger=logger)
logger.info("server_started", node_id=NODE_ID, peers=PEERS)

# Teammate 2: Replicated log integration (including undo/redo)
log_store = LogStore(NODE_ID, enable_hashing=True)
commit_manager = CommitManager(NODE_ID, PEERS)
undo_manager = UndoManager(NODE_ID)


class VoteRequest(BaseModel):
    term: int
    candidate_id: str


class HeartbeatRequest(BaseModel):
    term: int
    leader_id: str


class AppendEntriesRequest(BaseModel):
    term: int
    leader_id: str
    prev_log_index: int
    prev_log_term: int
    entries: list[dict[str, Any]]
    leader_commit: int


class SubmitStrokeRequest(BaseModel):
    stroke: dict[str, Any]


class UndoRequest(BaseModel):
    stroke_index: int


class RedoRequest(BaseModel):
    stroke_index: int


class SyncLogRequest(BaseModel):
    from_index: int


@app.post("/request-vote")
def request_vote(req: VoteRequest) -> dict:
    return node.handle_request_vote(req.term, req.candidate_id)


@app.post("/heartbeat")
def heartbeat(req: HeartbeatRequest) -> dict:
    return node.handle_heartbeat(req.term, req.leader_id)


@app.post("/append-entries")
def append_entries(req: AppendEntriesRequest) -> dict:
    """
    Teammate 2: Handle AppendEntries RPC from leader.
    Replicate log entries and track acknowledgments.
    """
    response = handle_append_entries(
        log_store,
        node.current_term,
        node.node_id,
        req.model_dump()
    )
    logger.info("append_entries_handled", success=response["success"], last_index=response["last_log_index"])
    return response


@app.get("/state")
def get_state() -> dict:
    return {
        "node_id": node.node_id,
        "state": node.state.value,
        "term": node.current_term,
        "leader": node.leader_id,
    }


@app.post("/submit-stroke")
def submit_stroke(req: SubmitStrokeRequest) -> dict:
    """
    Gateway API contract:
    POST /submit-stroke -> { success: true }

    Teammate 2: Only leader accepts strokes. Followers must reject.
    """
    if node.state != NodeState.LEADER:
        return {"success": False, "error": "Not leader"}

    from replica.log.models import Stroke
    stroke = Stroke(**req.stroke)
    entry = log_store.append(node.current_term, stroke)
    commit_manager.record_self_ack(entry.index)

    logger.info("stroke_appended", index=entry.index, term=entry.term)
    return {"success": True}


@app.get("/leader")
def get_leader() -> dict:
    """
    Gateway API contract:
    GET /leader -> { isLeader: true/false }
    """
    return {"isLeader": node.state == NodeState.LEADER}


@app.get("/status")
def get_status() -> dict:
    """
    Gateway API contract:
    GET /status -> { node, isLeader, logSize }

    Teammate 2: Return actual log store size.
    """
    return {
        "node": node.node_id,
        "isLeader": node.state == NodeState.LEADER,
        "logSize": log_store.get_log_size(),
    }


@app.post("/sync-log")
def sync_log(req: SyncLogRequest) -> dict:
    entries = [e.model_dump() for e in log_store.get_committed_entries_from(req.from_index)]
    return {
        "entries": entries,
        "last_index": log_store.get_last_index(),
    }


@app.post("/undo")
def undo(req: UndoRequest) -> dict:
    """
    Bonus Feature: Undo via log compensation.
    Only leader accepts undo requests.
    
    Appends UNDO entry to log, which marks stroke as "undone".
    Frontend filters out undone strokes from rendering.
    """
    if node.state != NodeState.LEADER:
        return {"success": False, "error": "Not leader"}

    stroke_index = req.stroke_index
    
    # Check if stroke exists
    if stroke_index < 0 or stroke_index >= log_store.get_log_size():
        return {"success": False, "error": "Invalid stroke index"}

    entry = log_store.append(
        term=node.current_term,
        stroke=None,
        entry_type=EntryType.UNDO,
        stroke_index=stroke_index
    )
    commit_manager.record_self_ack(entry.index)
    
    if undo_manager.mark_undo(stroke_index):
        logger.info("undo_appended", stroke_index=stroke_index, undo_entry_index=entry.index)
        return {"success": True}
    else:
        return {"success": False, "error": "Stroke already undone"}


@app.post("/redo")
def redo(req: RedoRequest) -> dict:
    """
    Bonus Feature: Redo via log compensation.
    Only leader accepts redo requests.
    
    Appends REDO entry to log, which marks undone stroke as active again.
    """
    if node.state != NodeState.LEADER:
        return {"success": False, "error": "Not leader"}

    stroke_index = req.stroke_index
    
    # Check if stroke exists
    if stroke_index < 0 or stroke_index >= log_store.get_log_size():
        return {"success": False, "error": "Invalid stroke index"}

    entry = log_store.append(
        term=node.current_term,
        stroke=None,
        entry_type=EntryType.REDO,
        stroke_index=stroke_index
    )
    commit_manager.record_self_ack(entry.index)
    
    if undo_manager.mark_redo(stroke_index):
        logger.info("redo_appended", stroke_index=stroke_index, redo_entry_index=entry.index)
        return {"success": True}
    else:
        return {"success": False, "error": "Stroke is not undone"}


@app.get("/log-integrity")
def check_log_integrity() -> dict:
    """
    Bonus Feature: Log integrity validation.
    Validates all entries have correct SHA256 hashes.
    """
    is_valid = log_store.validate_all_entries()
    return {
        "valid": is_valid,
        "log_size": log_store.get_log_size(),
        "hashing_enabled": log_store.enable_hashing,
    }


# TODO: Add Gateway API endpoints when Teammate 4 integration is ready.
# Example placeholders:
# - POST /query-leader
# - POST /election-ready
