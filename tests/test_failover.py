import asyncio
from unittest.mock import patch

from replica.recovery.restart_recovery import RecoveryLayer
from replica.consensus.state import NodeState


def test_failover_leader_crash_rejoin_sync() -> None:
    old_leader = {"id": "node1", "state": NodeState.LEADER, "term": 5}
    new_leader = {"id": "node2", "state": NodeState.FOLLOWER, "term": 5}

    old_leader["state"] = NodeState.FOLLOWER
    new_leader["state"] = NodeState.LEADER
    new_leader["term"] = 6

    assert new_leader["state"] == NodeState.LEADER
    assert new_leader["term"] == 6

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