import asyncio

from replica.recovery.consistency_checker import ConsistencyChecker
from replica.recovery.reconciliation_engine import ReconciliationEngine


def test_multi_failure_reconciliation_replaces_conflict_index() -> None:
    local = [
        {"index": 0, "term": 1, "is_committed": True},
        {"index": 1, "term": 2, "is_committed": False},
    ]
    engine = ReconciliationEngine(local)

    async def fake_fetch(_: str, __: int):
        return [
            {"index": 1, "term": 3, "is_committed": False},
            {"index": 2, "term": 3, "is_committed": False},
        ]

    engine.fetch_from_leader = fake_fetch  # type: ignore[assignment]
    asyncio.run(engine.reconcile("http://leader", 1))

    assert local[1]["term"] == 3
    assert len(local) == 3


def test_multi_failure_consistency_hash_matches_identical_logs() -> None:
    checker = ConsistencyChecker()
    leader = [
        {"index": 0, "term": 1, "is_committed": True},
        {"index": 1, "term": 1, "is_committed": True},
    ]
    follower = [
        {"index": 0, "term": 1, "is_committed": True},
        {"index": 1, "term": 1, "is_committed": True},
    ]

    assert checker.hash_matches_leader(follower, leader)