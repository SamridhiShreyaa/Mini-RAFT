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
    points: list[dict[str, float]]
    color: str
    timestamp: int


class LogEntry(BaseModel):
    """RAFT log entry containing a stroke or undo/redo compensation."""
    term: int
    index: int
    entry_type: EntryType = EntryType.STROKE
    stroke: Optional[Stroke] = None
    stroke_index: Optional[int] = None
    hash: Optional[str] = None
    is_committed: bool = False


class AppendEntriesRequest(BaseModel):
    """AppendEntries RPC request from leader."""
    term: int
    leader_id: str
    prev_log_index: int
    prev_log_term: int
    entries: list[dict[str, Any]]
    leader_commit: int


class AppendEntriesResponse(BaseModel):
    """Follower response to AppendEntries."""
    term: int
    success: bool
    last_log_index: int


class SyncLogRequest(BaseModel):
    """Request to sync missing log entries from index N onward."""
    from_index: int


class SyncLogResponse(BaseModel):
    """Response with all committed entries from index N onward."""
    entries: list[LogEntry]
    last_index: int
