from unittest.mock import patch

from replica.consensus.node import RaftNode
from replica.consensus.state import NodeState


class _NoopThread:
    def __init__(self, *args, **kwargs):
        pass

    def start(self):
        return None


@patch("replica.consensus.node.threading.Thread", new=_NoopThread)
def test_kill_leader_new_leader_selected() -> None:
    old_leader = RaftNode("node1", ["http://n2", "http://n3"])
    old_leader.state = NodeState.LEADER
    old_leader.current_term = 3

    follower = RaftNode("node2", ["http://n1", "http://n3"])
    follower.current_term = 3

    votes = iter([(True, 4), (True, 4)])

    def fake_vote(_: str, __: int):
        return next(votes)

    follower._request_vote = fake_vote  # type: ignore[assignment]
    follower.start_election()

    assert old_leader.state == NodeState.LEADER
    assert follower.state == NodeState.LEADER
    assert follower.current_term == 4