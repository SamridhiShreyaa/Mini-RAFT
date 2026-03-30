from pydantic import BaseModel
from typing import Any, Optional
from enum import Enum


class EntryType(str, Enum):
    """Types of log entries."""
    STROKE = "stroke"
    UNDO = "undo"
    REDO = "redo"


class Stroke(BaseModel):
    """User drawing stroke."""
    user_id: str
    points: list[dict[str, float]]  # [{x, y}, ...]
    color: str
    timestamp: int


class LogEntry(BaseModel):
    """RAFT log entry containing a stroke or undo/redo compensation."""
    term: int
    index: int
    entry_type: EntryType = EntryType.STROKE  # stroke, undo, or redo
    stroke: Optional[Stroke] = None  # Only for STROKE entries
    stroke_index: Optional[int] = None  # For UNDO/REDO: which stroke to undo/redo
    hash: Optional[str] = None  # SHA256 hash for integrity validation
    is_committed: bool = False


class AppendEntriesRequest(BaseModel):
    """AppendEntries RPC request from leader."""
    term: int
    leader_id: str
    prev_log_index: int
    prev_log_term: int
    entries: list[dict[str, Any]]  # Raw stroke data
    leader_commit: int


class AppendEntriesResponse(BaseModel):
    """Follower response to AppendEntries."""
    term: int
    success: bool
    last_log_index: int  # For leader to know where to retry


class SyncLogRequest(BaseModel):
    """Request to sync missing log entries from index N onward."""
    from_index: int


class SyncLogResponse(BaseModel):
    """Response with all committed entries from index N onward."""
    entries: list[LogEntry]
    last_index: int
