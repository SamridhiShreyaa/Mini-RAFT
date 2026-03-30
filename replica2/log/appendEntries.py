from typing import Dict, Any
from .models import LogEntry, Stroke, AppendEntriesResponse
from .logStore import LogStore


def handle_append_entries(
    log_store: LogStore,
    current_term: int,
    node_id: str,
    req_data: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Handle AppendEntries RPC from leader.
    Validates entries and appends to log if valid.

    Returns: { term, success, last_log_index }
    """
    leader_id = req_data.get("leader_id", "?")
    prev_log_index = req_data.get("prev_log_index", -1)
    prev_log_term = req_data.get("prev_log_term", 0)
    entries = req_data.get("entries", [])
    leader_commit = req_data.get("leader_commit", -1)
    req_term = req_data.get("term", 0)

    last_log_index = log_store.get_last_index()

    # Check 1: Reject if request term is stale
    if req_term < current_term:
        return {
            "term": current_term,
            "success": False,
            "last_log_index": last_log_index,
        }

    # Check 2: Validate prevLogIndex/prevLogTerm match
    if prev_log_index >= 0:
        prev_entry = log_store.get_entry(prev_log_index)
        if prev_entry is None or prev_entry.term != prev_log_term:
            # Log mismatch: return current log size for leader to retry
            return {
                "term": current_term,
                "success": False,
                "last_log_index": last_log_index,
                "reconcile_needed": True,
                "conflict_at": prev_log_index,
            }

    # Check 3: Append new entries (idempotent)
    next_expected = prev_log_index + 1
    for offset, entry_data in enumerate(entries):
        incoming_index = entry_data.get("index", next_expected + offset)
        if incoming_index != next_expected + offset:
            return {
                "term": current_term,
                "success": False,
                "last_log_index": log_store.get_last_index(),
                "reconcile_needed": True,
                "conflict_at": incoming_index,
            }
        stroke = Stroke(**entry_data.get("stroke", {}))
        log_store.append(entry_data.get("term", current_term), stroke)

    # Update committed entries if leader advances
    if leader_commit > -1:
        log_store.mark_committed(leader_commit)

    last_log_index = log_store.get_last_index()

    return {
        "term": current_term,
        "success": True,
        "last_log_index": last_log_index,
    }
