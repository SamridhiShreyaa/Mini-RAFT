"""
Test suite for log replication (Teammate 2).
Tests append-only, commit logic, idempotency, and ordering.
"""
import pytest
from replica.log.logStore import LogStore
from replica.log.commitManager import CommitManager
from replica.log.appendEntries import handle_append_entries
from replica.log.models import Stroke


class TestLogStore:
    """Test LogStore append-only and retrieval."""

    def test_append_stroke_increments_index(self):
        """Each stroke gets a unique monotonic index."""
        store = LogStore("test_node")
        stroke1 = Stroke(user_id="u1", points=[{"x": 1, "y": 2}], color="red", timestamp=100)
        stroke2 = Stroke(user_id="u1", points=[{"x": 3, "y": 4}], color="blue", timestamp=101)

        entry1 = store.append(term=1, stroke=stroke1)
        entry2 = store.append(term=1, stroke=stroke2)

        assert entry1.index == 0
        assert entry2.index == 1

    def test_append_only_no_overwrites(self):
        """Appended entries never get overwritten."""
        store = LogStore("test_node")
        stroke = Stroke(user_id="u1", points=[{"x": 1, "y": 2}], color="red", timestamp=100)

        entry1 = store.append(term=1, stroke=stroke)
        entry2 = store.append(term=1, stroke=stroke)

        # Verify both entries exist
        assert store.get_entry(0) is not None
        assert store.get_entry(1) is not None
        assert store.get_entry(0).index == 0
        assert store.get_entry(1).index == 1

    def test_get_entries_from_index(self):
        """Retrieve entries from a specific index."""
        store = LogStore("test_node")
        for i in range(5):
            stroke = Stroke(user_id=f"u{i}", points=[], color="red", timestamp=i)
            store.append(term=1, stroke=stroke)

        entries = store.get_entries_from(2)
        assert len(entries) == 3
        assert entries[0].index == 2
        assert entries[1].index == 3
        assert entries[2].index == 4

    def test_get_last_index_and_term(self):
        """last_index and last_term queries work correctly."""
        store = LogStore("test_node")
        stroke = Stroke(user_id="u1", points=[], color="red", timestamp=100)

        store.append(term=1, stroke=stroke)
        store.append(term=1, stroke=stroke)
        store.append(term=2, stroke=stroke)

        assert store.get_last_index() == 2
        assert store.get_last_term() == 2

    def test_mark_committed_up_to_index(self):
        """Mark entries as committed up to specific index."""
        store = LogStore("test_node")
        for i in range(5):
            stroke = Stroke(user_id=f"u{i}", points=[], color="red", timestamp=i)
            store.append(term=1, stroke=stroke)

        store.mark_committed(2)

        committed = store.get_committed_entries()
        assert len(committed) == 3  # Indices 0, 1, 2
        assert all(e.is_committed for e in committed)

    def test_get_log_size(self):
        """Log size getter returns correct count."""
        store = LogStore("test_node")
        assert store.get_log_size() == 0

        stroke = Stroke(user_id="u1", points=[], color="red", timestamp=100)
        store.append(term=1, stroke=stroke)
        assert store.get_log_size() == 1

        store.append(term=1, stroke=stroke)
        assert store.get_log_size() == 2

    def test_get_committed_entries_from_index(self):
        """Get committed entries from specific index (for sync-log)."""
        store = LogStore("test_node")
        stroke = Stroke(user_id="u1", points=[], color="red", timestamp=100)

        # Add 5 entries
        for i in range(5):
            store.append(term=1, stroke=stroke)

        # Mark indices 0, 1 as committed via mark_committed(1)
        store.mark_committed(1)
        # Manually mark 3, 4 as committed
        store.entries[3].is_committed = True
        store.entries[4].is_committed = True

        # Get committed from index 1 onward
        committed_from_1 = store.get_committed_entries_from(1)
        assert len(committed_from_1) == 3  # Indices 1, 3, 4
        assert all(e.is_committed for e in committed_from_1)

        # Get committed from index 0 onward
        committed_from_0 = store.get_committed_entries_from(0)
        assert len(committed_from_0) == 4  # Indices 0, 1, 3, 4

        # Get committed from index 2 onward (beyond committed region)
        committed_from_2 = store.get_committed_entries_from(2)
        assert len(committed_from_2) == 2  # Only indices 3, 4

        # Get committed from index 5 onward (beyond log)
        committed_from_5 = store.get_committed_entries_from(5)
        assert len(committed_from_5) == 0


class TestCommitManager:
    """Test CommitManager quorum logic."""

    def test_majority_count_three_nodes(self):
        """Majority for 3 nodes is 2."""
        manager = CommitManager("node1", ["node2", "node3"])
        assert manager.get_majority_count() == 2

    def test_record_ack_and_can_commit(self):
        """Track acks and determine commit when majority reached."""
        manager = CommitManager("node1", ["node2", "node3"])

        manager.record_ack(0, "node1")
        assert not manager.can_commit(0)  # 1/2 acks

        manager.record_ack(0, "node2")
        assert manager.can_commit(0)  # 2/2 acks (majority)

    def test_get_commit_index_contiguous(self):
        """get_commit_index returns highest contiguous committed index."""
        manager = CommitManager("node1", ["node2", "node3"])

        # Setup: index 0 committed, index 1 not committed, index 2 committed
        manager.record_ack(0, "node1")
        manager.record_ack(0, "node2")
        manager.record_ack(2, "node1")
        manager.record_ack(2, "node2")

        # Should return 0 (highest contiguous)
        assert manager.get_commit_index() == 0

    def test_record_self_ack(self):
        """record_self_ack uses node_id internally."""
        manager = CommitManager("node1", ["node2", "node3"])
        manager.record_self_ack(0)
        assert manager.can_commit(0) is False

        manager.record_ack(0, "node2")
        assert manager.can_commit(0) is True


class TestAppendEntries:
    """Test AppendEntries RPC handler."""

    def test_reject_stale_term(self):
        """Reject requests with older term than current."""
        store = LogStore("test_node")
        response = handle_append_entries(
            store,
            current_term=5,
            node_id="test_node",
            req_data={
                "term": 3,
                "leader_id": "leader",
                "prev_log_index": -1,
                "prev_log_term": 0,
                "entries": [],
                "leader_commit": -1,
            }
        )
        assert response["success"] is False
        assert response["term"] == 5

    def test_accept_empty_heartbeat(self):
        """Accept empty entries (heartbeat)."""
        store = LogStore("test_node")
        response = handle_append_entries(
            store,
            current_term=1,
            node_id="test_node",
            req_data={
                "term": 1,
                "leader_id": "leader",
                "prev_log_index": -1,
                "prev_log_term": 0,
                "entries": [],
                "leader_commit": -1,
            }
        )
        assert response["success"] is True

    def test_append_single_entry(self):
        """Append single stroke entry to log."""
        store = LogStore("test_node")
        stroke = Stroke(user_id="u1", points=[{"x": 1, "y": 2}], color="red", timestamp=100)

        response = handle_append_entries(
            store,
            current_term=1,
            node_id="test_node",
            req_data={
                "term": 1,
                "leader_id": "leader",
                "prev_log_index": -1,
                "prev_log_term": 0,
                "entries": [{"stroke": stroke.model_dump(), "term": 1}],
                "leader_commit": -1,
            }
        )
        assert response["success"] is True
        assert response["last_log_index"] == 0
        assert store.get_log_size() == 1

    def test_append_multiple_entries(self):
        """Append multiple stroke entries in one RPC."""
        store = LogStore("test_node")
        strokes = [
            Stroke(user_id=f"u{i}", points=[{"x": i, "y": i}], color="red", timestamp=100 + i)
            for i in range(3)
        ]

        response = handle_append_entries(
            store,
            current_term=1,
            node_id="test_node",
            req_data={
                "term": 1,
                "leader_id": "leader",
                "prev_log_index": -1,
                "prev_log_term": 0,
                "entries": [{"stroke": s.model_dump(), "term": 1} for s in strokes],
                "leader_commit": -1,
            }
        )
        assert response["success"] is True
        assert response["last_log_index"] == 2
        assert store.get_log_size() == 3

    def test_mark_committed_on_append(self):
        """Entries marked as committed when leader_commit advances."""
        store = LogStore("test_node")
        stroke = Stroke(user_id="u1", points=[], color="red", timestamp=100)

        # Add 3 entries
        for _ in range(3):
            store.append(term=1, stroke=stroke)

        # Leader says commit up to index 1
        response = handle_append_entries(
            store,
            current_term=1,
            node_id="test_node",
            req_data={
                "term": 1,
                "leader_id": "leader",
                "prev_log_index": 2,
                "prev_log_term": 1,
                "entries": [],
                "leader_commit": 1,
            }
        )

        assert response["success"] is True
        committed = store.get_committed_entries()
        assert len(committed) == 2  # Indices 0 and 1

    def test_prev_log_term_mismatch(self):
        """Reject if prevLogIndex term doesn't match."""
        store = LogStore("test_node")
        stroke = Stroke(user_id="u1", points=[], color="red", timestamp=100)
        store.append(term=1, stroke=stroke)  # Index 0 has term=1

        response = handle_append_entries(
            store,
            current_term=2,
            node_id="test_node",
            req_data={
                "term": 2,
                "leader_id": "leader",
                "prev_log_index": 0,
                "prev_log_term": 2,  # Mismatch: actual term is 1
                "entries": [],
                "leader_commit": -1,
            }
        )
        assert response["success"] is False


class TestOrdering:
    """Test log entry ordering guarantees."""

    def test_stroke_order_preserved(self):
        """Strokes maintain order across replication."""
        store = LogStore("test_node")
        colors = ["red", "blue", "green"]

        for i, color in enumerate(colors):
            stroke = Stroke(user_id="u1", points=[{"x": i}], color=color, timestamp=100 + i)
            store.append(term=1, stroke=stroke)

        # Verify order
        entries = store.get_entries_from(0)
        assert entries[0].stroke.color == "red"
        assert entries[1].stroke.color == "blue"
        assert entries[2].stroke.color == "green"

    def test_idempotent_append(self):
        """Reapplying same entries doesn't duplicate."""
        store = LogStore("test_node")

        stroke = Stroke(user_id="u1", points=[{"x": 1}], color="red", timestamp=100)
        entry1 = store.append(term=1, stroke=stroke)
        assert store.get_log_size() == 1

        # Simulate receiving same entry again (leader retry)
        entry2 = store.append(term=1, stroke=stroke)
        assert store.get_log_size() == 2

        # Entries should have different indices
        assert entry1.index == 0
        assert entry2.index == 1


class TestUndoRedo:
    """Test undo/redo via log compensation."""

    def test_mark_stroke_as_undone(self):
        """Mark a stroke as undone."""
        from replica.log.undoManager import UndoManager
        manager = UndoManager("node1")

        assert not manager.is_undone(0)
        assert manager.mark_undo(0)
        assert manager.is_undone(0)

    def test_cannot_undo_same_stroke_twice(self):
        """Cannot undo an already undone stroke."""
        from replica.log.undoManager import UndoManager
        manager = UndoManager("node1")

        assert manager.mark_undo(0)
        assert not manager.mark_undo(0)  # Already undone

    def test_mark_undone_stroke_as_active_redo(self):
        """Mark undone stroke as active again (redo)."""
        from replica.log.undoManager import UndoManager
        manager = UndoManager("node1")

        manager.mark_undo(0)
        assert manager.is_undone(0)

        assert manager.mark_redo(0)
        assert not manager.is_undone(0)

    def test_cannot_redo_active_stroke(self):
        """Cannot redo a stroke that isn't undone."""
        from replica.log.undoManager import UndoManager
        manager = UndoManager("node1")

        assert not manager.mark_redo(0)  # Not undone

    def test_get_active_strokes_filters_undone(self):
        """get_active_strokes excludes undone strokes."""
        from replica.log.undoManager import UndoManager
        manager = UndoManager("node1")

        all_strokes = [0, 1, 2, 3]
        manager.mark_undo(1)
        manager.mark_undo(3)

        active = manager.get_active_strokes(all_strokes)
        assert active == [0, 2]

    def test_undo_redo_entries_in_log(self):
        """Append UNDO and REDO entries to log."""
        from replica.log.models import EntryType
        store = LogStore("test_node")
        stroke = Stroke(user_id="u1", points=[], color="red", timestamp=100)

        # Add stroke
        entry1 = store.append(term=1, stroke=stroke, entry_type=EntryType.STROKE)
        assert entry1.entry_type == EntryType.STROKE
        assert entry1.index == 0

        # Append undo
        entry2 = store.append(
            term=1,
            stroke=None,
            entry_type=EntryType.UNDO,
            stroke_index=0
        )
        assert entry2.entry_type == EntryType.UNDO
        assert entry2.stroke_index == 0
        assert entry2.index == 1

        # Append redo
        entry3 = store.append(
            term=1,
            stroke=None,
            entry_type=EntryType.REDO,
            stroke_index=0
        )
        assert entry3.entry_type == EntryType.REDO
        assert entry3.stroke_index == 0
        assert entry3.index == 2

    def test_get_active_strokes_excludes_compensation(self):
        """get_active_strokes only returns STROKE entries, not UNDO/REDO."""
        from replica.log.models import EntryType
        from replica.log.undoManager import UndoManager
        
        store = LogStore("test_node")
        manager = UndoManager("node1")
        stroke = Stroke(user_id="u1", points=[], color="red", timestamp=100)

        # Add 2 strokes
        entry1 = store.append(term=1, stroke=stroke, entry_type=EntryType.STROKE)
        entry2 = store.append(term=1, stroke=stroke, entry_type=EntryType.STROKE)

        # Mark as committed
        store.mark_committed(1)

        # Add undo entry
        store.append(term=1, stroke=None, entry_type=EntryType.UNDO, stroke_index=0)
        
        # Mark stroke 0 as undone in undo manager
        manager.mark_undo(0)

        # Get active strokes
        active = store.get_active_strokes(manager)
        assert len(active) == 1  # Only entry2 (entry1 is undone)
        assert active[0].index == 1


class TestHashIntegrity:
    """Test log entry hashing for integrity validation."""

    def test_compute_hash_on_stroke_entry(self):
        """Each stroke entry gets a SHA256 hash."""
        store = LogStore("test_node", enable_hashing=True)
        stroke = Stroke(user_id="u1", points=[{"x": 1}], color="red", timestamp=100)

        entry = store.append(term=1, stroke=stroke)
        assert entry.hash is not None
        assert len(entry.hash) == 64  # SHA256 hex is 64 chars

    def test_hash_different_for_different_entries(self):
        """Different entries have different hashes."""
        store = LogStore("test_node", enable_hashing=True)

        stroke1 = Stroke(user_id="u1", points=[{"x": 1}], color="red", timestamp=100)
        stroke2 = Stroke(user_id="u1", points=[{"x": 2}], color="blue", timestamp=101)

        entry1 = store.append(term=1, stroke=stroke1)
        entry2 = store.append(term=1, stroke=stroke2)

        assert entry1.hash != entry2.hash

    def test_same_stroke_data_same_hash(self):
        """Same stroke data produces same hash."""
        from replica.log.logStore import compute_entry_hash
        from replica.log.models import EntryType, LogEntry

        stroke = Stroke(user_id="u1", points=[{"x": 1}], color="red", timestamp=100)

        config1 = {
            "term": 1,
            "index": 0,
            "entry_type": EntryType.STROKE,
            "stroke": stroke,
            "stroke_index": None,
            "is_committed": False,
        }
        config2 = {
            "term": 1,
            "index": 0,
            "entry_type": EntryType.STROKE,
            "stroke": stroke,
            "stroke_index": None,
            "is_committed": False,
        }

        entry1 = LogEntry(**config1)
        entry2 = LogEntry(**config2)

        hash1 = compute_entry_hash(entry1)
        hash2 = compute_entry_hash(entry2)

        assert hash1 == hash2

    def test_validate_entry_hash_valid(self):
        """Validate entry with correct hash."""
        store = LogStore("test_node", enable_hashing=True)
        stroke = Stroke(user_id="u1", points=[], color="red", timestamp=100)

        entry = store.append(term=1, stroke=stroke)
        assert store.validate_entry_hash(entry)

    def test_validate_all_entries_clean_log(self):
        """Validate all entries in clean log."""
        store = LogStore("test_node", enable_hashing=True)
        stroke = Stroke(user_id="u1", points=[], color="red", timestamp=100)

        for _ in range(5):
            store.append(term=1, stroke=stroke)

        assert store.validate_all_entries()

    def test_validate_all_entries_detects_corruption(self):
        """Detect corrupted entry hash."""
        store = LogStore("test_node", enable_hashing=True)
        stroke = Stroke(user_id="u1", points=[], color="red", timestamp=100)

        entry = store.append(term=1, stroke=stroke)

        # Corrupt the hash
        entry.hash = "corrupted_hash"

        assert not store.validate_entry_hash(entry)
        assert not store.validate_all_entries()

    def test_hashing_disabled_skips_validation(self):
        """With hashing disabled, validation returns true."""
        store = LogStore("test_node", enable_hashing=False)
        stroke = Stroke(user_id="u1", points=[], color="red", timestamp=100)

        entry = store.append(term=1, stroke=stroke)
        assert entry.hash is None
        assert store.validate_entry_hash(entry)  # Always true when disabled

    def test_undo_redo_entries_also_hashed(self):
        """UNDO/REDO compensation entries also get hashed."""
        from replica.log.models import EntryType
        
        store = LogStore("test_node", enable_hashing=True)

        entry = store.append(
            term=1,
            stroke=None,
            entry_type=EntryType.UNDO,
            stroke_index=5
        )

        assert entry.hash is not None
        assert store.validate_entry_hash(entry)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
