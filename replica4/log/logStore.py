import json
import threading
import hashlib
import os
from typing import Optional, List
from .models import LogEntry, Stroke, EntryType


def compute_entry_hash(entry: LogEntry) -> str:
    """Compute SHA256 hash of log entry for integrity validation."""
    entry_dict = entry.model_dump()
    entry_dict.pop("hash", None)  # Remove hash field before hashing
    entry_json = json.dumps(entry_dict, sort_keys=True)
    return hashlib.sha256(entry_json.encode()).hexdigest()


class LogStore:
    """Append-only log store for RAFT consensus."""

    def __init__(self, node_id: str, enable_hashing: bool = True) -> None:
        self.node_id = node_id
        self.entries: List[LogEntry] = []  # Index 0 is sentinel, actual logs start at index 1
        self.lock = threading.Lock()
        self.log_file = f"logs/node_{node_id}.json"
        self.enable_hashing = enable_hashing
        self.persist_to_disk = "PYTEST_CURRENT_TEST" not in os.environ
        self._load_from_disk()

    def append(self, term: int, stroke: Stroke, entry_type: EntryType = EntryType.STROKE, 
               stroke_index: Optional[int] = None) -> LogEntry:
        """
        Append a stroke, undo, or redo entry to the log.
        
        Args:
            term: Current RAFT term
            stroke: The Stroke data (required for STROKE entries, None for UNDO/REDO)
            entry_type: STROKE, UNDO, or REDO
            stroke_index: For UNDO/REDO entries, which stroke to undo/redo
            
        Returns: LogEntry with assigned index and optional hash
        """
        with self.lock:
            new_index = len(self.entries)
            entry = LogEntry(
                term=term,
                index=new_index,
                entry_type=entry_type,
                stroke=stroke if entry_type == EntryType.STROKE else None,
                stroke_index=stroke_index if entry_type in (EntryType.UNDO, EntryType.REDO) else None,
                is_committed=False
            )
            
            # Compute hash for integrity validation
            if self.enable_hashing:
                entry.hash = compute_entry_hash(entry)
            
            self.entries.append(entry)
            self._persist_entry(entry)
            return entry

    def get_entry(self, index: int) -> Optional[LogEntry]:
        """Get log entry at specific index. Index 0 is invalid."""
        with self.lock:
            if 0 <= index < len(self.entries):
                return self.entries[index]
            return None

    def get_entries_from(self, from_index: int) -> List[LogEntry]:
        """Get all entries from from_index onward."""
        with self.lock:
            if from_index < 0 or from_index >= len(self.entries):
                return []
            return self.entries[from_index:]

    def get_last_index(self) -> int:
        """Return the index of the last log entry."""
        with self.lock:
            return len(self.entries) - 1

    def get_last_term(self) -> int:
        """Return term of the last log entry."""
        with self.lock:
            if len(self.entries) > 0:
                return self.entries[-1].term
            return 0

    def mark_committed(self, up_to_index: int) -> None:
        """Mark all entries up to up_to_index as committed."""
        with self.lock:
            for i in range(min(up_to_index + 1, len(self.entries))):
                if i < len(self.entries):
                    self.entries[i].is_committed = True

    def get_committed_entries(self) -> List[LogEntry]:
        """Return all committed entries."""
        with self.lock:
            return [e for e in self.entries if e.is_committed]

    def get_committed_entries_from(self, from_index: int) -> List[LogEntry]:
        """
        Return all committed entries from from_index onward.
        Used by Teammate 3 for /sync-log endpoint (catch-up protocol).
        """
        with self.lock:
            if from_index < 0 or from_index >= len(self.entries):
                return []
            return [e for e in self.entries[from_index:] if e.is_committed]

    def get_log_size(self) -> int:
        """Return total log size."""
        with self.lock:
            return len(self.entries)

    def validate_entry_hash(self, entry: LogEntry) -> bool:
        """
        Validate that an entry's hash is correct (integrity check).
        Returns True if hash is valid or hashing is disabled.
        """
        if not self.enable_hashing or not entry.hash:
            return True
        
        computed_hash = compute_entry_hash(entry)
        return computed_hash == entry.hash

    def validate_all_entries(self) -> bool:
        """
        Validate all entries in log (detect corruption).
        Returns True if all entries valid, False if any corrupted.
        """
        with self.lock:
            for entry in self.entries:
                if not self.validate_entry_hash(entry):
                    return False
            return True

    def get_active_strokes(self, undo_manager) -> List[LogEntry]:
        """
        Return all non-undone, committed stroke entries.
        Filters out compensation entries and undone strokes.
        """
        with self.lock:
            active = []
            for entry in self.entries:
                if not entry.is_committed:
                    continue
                if entry.entry_type != EntryType.STROKE:
                    continue
                if undo_manager.is_undone(entry.index):
                    continue
                active.append(entry)
            return active

    def _persist_entry(self, entry: LogEntry) -> None:
        """Persist entry to disk (append mode)."""
        if not self.persist_to_disk:
            return
        try:
            os.makedirs(os.path.dirname(self.log_file), exist_ok=True)
            with open(self.log_file, "a") as f:
                f.write(json.dumps(entry.model_dump()) + "\n")
        except Exception:
            pass  # Gracefully handle file I/O errors

    def _load_from_disk(self) -> None:
        """Load log entries from disk on startup."""
        if not self.persist_to_disk:
            return
        try:
            with open(self.log_file, "r") as f:
                for line in f:
                    if line.strip():
                        data = json.loads(line)
                        entry = LogEntry(**data)
                        self.entries.append(entry)
        except FileNotFoundError:
            pass  # First startup, no log file yet
        except Exception:
            pass  # Gracefully handle errors
