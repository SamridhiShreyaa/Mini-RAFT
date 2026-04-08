import threading
import time
from typing import Optional, Tuple

import requests
from shared.logger import ElectionLogger

from .state import NodeState
from .timer import ElectionTimer


class RaftNode:
    def __init__(
        self, node_id: str, peers: list[str], logger: Optional[ElectionLogger] = None
    ) -> None:
        self.node_id = node_id
        self.peers = peers
        self.logger = logger or ElectionLogger(node_id)

        self.state = NodeState.FOLLOWER
        self.current_term = 0
        self.voted_for: Optional[str] = None
        self.leader_id: Optional[str] = None

        self.election_timer = ElectionTimer()
        self.heartbeat_interval = 0.15

        self.votes_received = 0
        self.lock = threading.Lock()
        self.suspended = False

        self.logger.info(
            "node_initialized",
            peers=len(peers),
            election_timeout_range=(0.5, 0.8),
            heartbeat_interval=self.heartbeat_interval,
        )

        threading.Thread(target=self.run_election_loop, daemon=True).start()
        threading.Thread(target=self.run_heartbeat_loop, daemon=True).start()

    def _majority_count(self) -> int:
        total_nodes = len(self.peers) + 1
        return (total_nodes // 2) + 1

    def run_election_loop(self) -> None:
        while True:
            time.sleep(0.05)
            if self.suspended:
                continue
            with self.lock:
                should_start = self.state != NodeState.LEADER and self.election_timer.expired()
            if should_start:
                self.start_election()

    def start_election(self) -> None:
        with self.lock:
            self.state = NodeState.CANDIDATE
            self.current_term += 1
            election_term = self.current_term
            self.voted_for = self.node_id
            self.votes_received = 1
            self.election_timer.reset()
            self.logger.warning("election_started", term=election_term)

        for peer in self.peers:
            vote_granted, peer_term = self._request_vote(peer, election_term)

            with self.lock:
                # Candidate may have stepped down while waiting on network.
                if self.state != NodeState.CANDIDATE or self.current_term != election_term:
                    return

                if peer_term > self.current_term:
                    self.logger.warning(
                        "higher_term_seen_during_vote",
                        local_term=self.current_term,
                        peer_term=peer_term,
                    )
                    self.current_term = peer_term
                    self.state = NodeState.FOLLOWER
                    self.voted_for = None
                    self.leader_id = None
                    self.election_timer.reset()
                    return

                if vote_granted:
                    self.votes_received += 1

        with self.lock:
            if self.state == NodeState.CANDIDATE and self.current_term == election_term:
                if self.votes_received >= self._majority_count():
                    self.state = NodeState.LEADER
                    self.leader_id = self.node_id
                    self.logger.info("became_leader", term=self.current_term)

    def _request_vote(self, peer: str, election_term: int) -> Tuple[bool, int]:
        try:
            res = requests.post(
                f"{peer}/request-vote",
                json={"term": election_term, "candidate_id": self.node_id},
                timeout=0.3,
            )
            data = res.json() if res.ok else {}
            vote_granted = bool(data.get("vote_granted", False))
            peer_term = int(data.get("term", election_term))
            self.logger.info(
                "vote_response",
                peer=peer,
                vote_granted=vote_granted,
                peer_term=peer_term,
                election_term=election_term,
            )
            return vote_granted, peer_term
        except (requests.RequestException, ValueError, TypeError):
            self.logger.warning("vote_request_failed", peer=peer, election_term=election_term)
            return False, election_term

    def run_heartbeat_loop(self) -> None:
        while True:
            time.sleep(self.heartbeat_interval)
            if self.suspended:
                continue
            with self.lock:
                if self.state != NodeState.LEADER:
                    continue
                heartbeat_term = self.current_term

            for peer in self.peers:
                self._send_heartbeat(peer, heartbeat_term)

    def _send_heartbeat(self, peer: str, heartbeat_term: int) -> None:
        try:
            res = requests.post(
                f"{peer}/heartbeat",
                json={"term": heartbeat_term, "leader_id": self.node_id},
                timeout=0.2,
            )
            if not res.ok:
                return
            data = res.json()
            peer_term = int(data.get("term", heartbeat_term))

            with self.lock:
                if peer_term > self.current_term:
                    self.logger.warning(
                        "higher_term_seen_during_heartbeat",
                        local_term=self.current_term,
                        peer_term=peer_term,
                        peer=peer,
                    )
                    self.current_term = peer_term
                    self.state = NodeState.FOLLOWER
                    self.voted_for = None
                    self.leader_id = None
                    self.election_timer.reset()
        except (requests.RequestException, ValueError, TypeError):
            self.logger.warning("heartbeat_send_failed", peer=peer, heartbeat_term=heartbeat_term)
            return

    def handle_request_vote(self, term: int, candidate_id: str) -> dict:
        with self.lock:
            if term < self.current_term:
                self.logger.info(
                    "vote_rejected_stale_term",
                    request_term=term,
                    current_term=self.current_term,
                    candidate_id=candidate_id,
                )
                return {"term": self.current_term, "vote_granted": False}

            if term > self.current_term:
                self.logger.warning(
                    "term_updated_from_vote",
                    old_term=self.current_term,
                    new_term=term,
                    candidate_id=candidate_id,
                )
                self.current_term = term
                self.state = NodeState.FOLLOWER
                self.voted_for = None
                self.leader_id = None

            if self.voted_for is None or self.voted_for == candidate_id:
                self.voted_for = candidate_id
                self.election_timer.reset()
                self.logger.info(
                    "vote_granted", term=self.current_term, candidate_id=candidate_id
                )
                return {"term": self.current_term, "vote_granted": True}

            self.logger.info(
                "vote_rejected_already_voted",
                term=self.current_term,
                voted_for=self.voted_for,
                candidate_id=candidate_id,
            )
            return {"term": self.current_term, "vote_granted": False}

    def handle_heartbeat(self, term: int, leader_id: str) -> dict:
        with self.lock:
            if term < self.current_term:
                self.logger.info(
                    "heartbeat_rejected_stale_term",
                    request_term=term,
                    current_term=self.current_term,
                    leader_id=leader_id,
                )
                return {"term": self.current_term, "success": False, "status": "stale"}

            if term > self.current_term:
                self.logger.warning(
                    "term_updated_from_heartbeat",
                    old_term=self.current_term,
                    new_term=term,
                    leader_id=leader_id,
                )
                self.current_term = term

            self.state = NodeState.FOLLOWER
            self.leader_id = leader_id
            self.voted_for = None
            self.election_timer.reset()
            self.logger.info("heartbeat_accepted", term=self.current_term, leader_id=leader_id)
            return {"term": self.current_term, "success": True, "status": "ok"}

    def suspend(self) -> None:
        with self.lock:
            self.suspended = True
            # Simulate volatile state memory wipe
            self.state = NodeState.FOLLOWER
            self.leader_id = None
            self.voted_for = None
            self.votes_received = 0

    def resume(self) -> None:
        with self.lock:
            self.suspended = False
            self.election_timer.reset()

