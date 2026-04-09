import threading
from typing import Set, Dict, Optional
from .models import EntryType


class UndoManager:
    """
    Manages undo/redo state by tracking which strokes are "undone".
    
    In RAFT, we never delete entries. Instead:
    - UNDO: append compensation entry marking stroke as undone
    - REDO: append compensation entry remarking stroke as active
    - Frontend filters out "undone" strokes from rendering
    """

    def __init__(self, node_id: str) -> None:
        self.node_id = node_id
        self.undone_strokes: Set[int] = set()
        self.redo_stack: list[int] = []
        self.lock = threading.Lock()

    def mark_undo(self, stroke_index: int) -> bool:
        """
        Mark a stroke as undone.
        Returns True if successfully undone, False if already undone.
        """
        with self.lock:
            if stroke_index in self.undone_strokes:
                return False
            
            self.undone_strokes.add(stroke_index)
            self.redo_stack.clear()
            return True

    def mark_redo(self, stroke_index: int) -> bool:
        """
        Mark an undone stroke as active again (redo).
        Returns True if successfully redone, False if not undone.
        """
        with self.lock:
            if stroke_index not in self.undone_strokes:
                return False
            
            self.undone_strokes.remove(stroke_index)
            if stroke_index not in self.redo_stack:
                self.redo_stack.append(stroke_index)
            return True

    def is_undone(self, stroke_index: int) -> bool:
        """Check if a stroke is currently undone."""
        with self.lock:
            return stroke_index in self.undone_strokes

    def get_active_strokes(self, all_stroke_indices: list[int]) -> list[int]:
        """
        Return which strokes should be visible.
        Filters out undone strokes.
        """
        with self.lock:
            return [i for i in all_stroke_indices if i not in self.undone_strokes]

    def can_undo(self) -> bool:
        """Check if there are strokes that can be undone."""
        with self.lock:
            return len(self.undone_strokes) < 999

    def can_redo(self) -> bool:
        """Check if there are strokes that can be redone."""
        with self.lock:
            return len(self.redo_stack) > 0

    def clear_all(self) -> None:
        """Clear all undo/redo state (e.g., on new leader)."""
        with self.lock:
            self.undone_strokes.clear()
            self.redo_stack.clear()

    def get_state(self) -> dict:
        """Return current undo/redo state (for debugging)."""
        with self.lock:
            return {
                "undone_count": len(self.undone_strokes),
                "redo_stack_size": len(self.redo_stack),
            }
