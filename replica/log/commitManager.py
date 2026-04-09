import threading
from typing import Dict, Set


class CommitManager:
    """
    Tracks log entry replication across replicas.
    Determines when majority quorum is reached for each entry.
    """

    def __init__(self, node_id: str, peers: list[str]) -> None:
        self.node_id = node_id
        self.peers = peers
        self.total_nodes = len(peers) + 1
        self.majority = (self.total_nodes // 2) + 1

        self.ack_count: Dict[int, Set[str]] = {}
        self.lock = threading.Lock()

    def record_ack(self, log_index: int, from_node: str) -> None:
        """Record that a node has acknowledged replication up to log_index."""
        with self.lock:
            if log_index not in self.ack_count:
                self.ack_count[log_index] = set()
            self.ack_count[log_index].add(from_node)

    def record_self_ack(self, log_index: int) -> None:
        """Record that leader has the entry in its own log."""
        self.record_ack(log_index, self.node_id)

    def can_commit(self, log_index: int) -> bool:
        """
        Check if log_index has reached majority quorum.
        Returns True if enough replicas have acknowledged.
        """
        with self.lock:
            acks = self.ack_count.get(log_index, set())
            return len(acks) >= self.majority

    def get_commit_index(self) -> int:
        """
        Return the highest index that has reached majority quorum.
        Scans from the beginning to find the highest contiguous committed index.
        """
        with self.lock:
            commit_index = -1
            i = 0
            while i in self.ack_count and len(self.ack_count[i]) >= self.majority:
                commit_index = i
                i += 1
            return commit_index

    def clear_for_new_leader(self) -> None:
        """Clear all ack history when a new leader takes over."""
        with self.lock:
            self.ack_count.clear()

    def get_majority_count(self) -> int:
        """Return the number of nodes needed for majority."""
        return self.majority
