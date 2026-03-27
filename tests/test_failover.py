import asyncio
from unittest.mock import patch

from replica.consensus.state import NodeState
from replica.consensus.node import RaftNode
from replica.recovery.restart_recovery import RecoveryLayer


class _NoopThread:
    def __init__(self, *args, **kwargs):
        pass

    def start(self):
        return None


@patch("replica.consensus.node.threading.Thread", new=_NoopThread)
def test_failover_leader_crash_rejoin_sync() -> None:
    leader = RaftNode("node1", ["http://n2", "http://n3"])
    leader.state = NodeState.LEADER
    leader.current_term = 5

    new_leader = RaftNode("node2", ["http://n1", "http://n3"])
    new_leader.current_term = 5

    votes = iter([(True, 6), (True, 6)])

    def fake_vote(_: str, __: int):
        return next(votes)

    new_leader._request_vote = fake_vote  # type: ignore[assignment]
    new_leader.start_election()

    assert new_leader.state == NodeState.LEADER
    assert new_leader.current_term == 6

    restarted_old_leader = RecoveryLayer("node1")
    restarted_old_leader.memory_log = [{"index": 0, "term": 5, "is_committed": True}]

    class _Resp:
        ok = True

        @staticmethod
        def json() -> dict:
            return {
                "entries": [
                    {"index": 1, "term": 6, "is_committed": True},
                    {"index": 2, "term": 6, "is_committed": True},
                ]
            }

    with patch("replica.recovery.restart_recovery.requests.post", return_value=_Resp()):
        added = asyncio.run(restarted_old_leader.catch_up_with_leader("http://n2"))

    assert added == 2
    assert restarted_old_leader.memory_log[-1]["term"] == 6