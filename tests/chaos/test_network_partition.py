from unittest.mock import patch
import asyncio

from replica.consensus.node import RaftNode
from replica.consensus.state import NodeState
from replica.recovery.restart_recovery import RecoveryLayer


class _NoopThread:
    def __init__(self, *args, **kwargs):
        pass

    def start(self):
        return None


@patch("replica.consensus.node.threading.Thread", new=_NoopThread)
def test_majority_calculation_for_even_cluster() -> None:
    node = RaftNode("node1", ["http://n2", "http://n3", "http://n4"])
    assert node._majority_count() == 3


@patch("replica.consensus.node.threading.Thread", new=_NoopThread)
def test_candidate_steps_down_on_higher_term_vote_response() -> None:
    node = RaftNode("node1", ["http://n2", "http://n3"])

    responses = iter([
        (False, 8),
        (True, 2),
    ])

    def fake_request_vote(peer: str, election_term: int):
        return next(responses)

    node._request_vote = fake_request_vote  # type: ignore[assignment]
    node.current_term = 1

    node.start_election()

    assert node.state == NodeState.FOLLOWER
    assert node.current_term == 8


@patch("replica.consensus.node.threading.Thread", new=_NoopThread)
def test_minority_partition_cannot_elect_leader_in_4_node_cluster() -> None:
    node = RaftNode("node1", ["http://n2", "http://n3", "http://n4"])

    # Simulate partition where only one peer is reachable and grants vote.
    # Votes: self (1) + one peer (1) = 2, but majority needed is 3.
    responses = iter([
        (True, 1),
        (False, 1),
        (False, 1),
    ])

    def fake_request_vote(peer: str, election_term: int):
        return next(responses)

    node._request_vote = fake_request_vote  # type: ignore[assignment]
    node.current_term = 0

    node.start_election()

    assert node.votes_received == 2
    assert node._majority_count() == 3
    assert node.state != NodeState.LEADER


def test_partition_healed_replica_catches_up() -> None:
    recovery = RecoveryLayer("node4")
    recovery.memory_log = [{"index": 0, "term": 1, "is_committed": True}]

    class _Resp:
        ok = True

        @staticmethod
        def json() -> dict:
            return {
                "entries": [
                    {"index": 1, "term": 1, "is_committed": True},
                    {"index": 2, "term": 2, "is_committed": True},
                ]
            }

    with patch("replica.recovery.restart_recovery.requests.post", return_value=_Resp()):
        added = asyncio.run(recovery.catch_up_with_leader("http://leader"))

    assert added == 2
    assert len(recovery.memory_log) == 3
