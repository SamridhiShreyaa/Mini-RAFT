import os
from typing import Any

from fastapi import FastAPI
from pydantic import BaseModel

from .node import RaftNode
from .state import NodeState
from shared.logger import ElectionLogger

app = FastAPI(title="Mini-RAFT Consensus Server")

NODE_ID = os.getenv("NODE_ID", "1")
PEERS = [peer.strip() for peer in os.getenv("PEERS", "").split(",") if peer.strip()]

logger = ElectionLogger(NODE_ID)
node = RaftNode(NODE_ID, PEERS, logger=logger)
logger.info("server_started", node_id=NODE_ID, peers=PEERS)

# Temporary in-memory stroke store for Gateway API compatibility.
# TODO: Replace with Teammate 2 replicated log integration.
_stroke_log: list[dict[str, Any]] = []


class VoteRequest(BaseModel):
    term: int
    candidate_id: str


class HeartbeatRequest(BaseModel):
    term: int
    leader_id: str


class SubmitStrokeRequest(BaseModel):
    stroke: dict[str, Any]


@app.post("/request-vote")
def request_vote(req: VoteRequest) -> dict:
    return node.handle_request_vote(req.term, req.candidate_id)


@app.post("/heartbeat")
def heartbeat(req: HeartbeatRequest) -> dict:
    return node.handle_heartbeat(req.term, req.leader_id)


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
    """
    _stroke_log.append(req.stroke)
    logger.info("stroke_received", log_size=len(_stroke_log))
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
    """
    return {
        "node": node.node_id,
        "isLeader": node.state == NodeState.LEADER,
        "logSize": len(_stroke_log),
    }


# TODO: Add Gateway API endpoints when Teammate 4 integration is ready.
# Example placeholders:
# - POST /query-leader
# - POST /election-ready
