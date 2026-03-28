import asyncio
from unittest.mock import patch

from replica.recovery.restart_recovery import RecoveryLayer


def test_restart_replica_recovers_commit_index(tmp_path) -> None:
    recovery = RecoveryLayer("r2", disk_dir=str(tmp_path))
    recovery.append_recovered_entry({"index": 0, "term": 1, "is_committed": True})
    recovery.append_recovered_entry({"index": 1, "term": 1, "is_committed": True})
    recovery.append_recovered_entry({"index": 2, "term": 2, "is_committed": False})

    restarted = RecoveryLayer("r2", disk_dir=str(tmp_path))
    state = asyncio.run(restarted.bootstrap())

    assert state.commit_index == 1


def test_catchup_requests_missing_logs() -> None:
    recovery = RecoveryLayer("r3")
    recovery.memory_log = [{"index": 0, "term": 1, "is_committed": True}]

    class _Resp:
        ok = True

        @staticmethod
        def json() -> dict:
            return {
                "entries": [
                    {"index": 1, "term": 1, "is_committed": True},
                    {"index": 2, "term": 2, "is_committed": False},
                ]
            }

    with patch("replica.recovery.restart_recovery.requests.post", return_value=_Resp()):
        added = asyncio.run(recovery.catch_up_with_leader("http://leader"))

    assert added == 2
    assert len(recovery.memory_log) == 3