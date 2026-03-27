import hashlib
import json
from typing import Any


def _entry_hash(entry: dict[str, Any]) -> str:
    raw = dict(entry)
    raw.pop("hash", None)
    payload = json.dumps(raw, sort_keys=True)
    return hashlib.sha256(payload.encode()).hexdigest()


class ConsistencyChecker:
    def no_committed_overwrite(
        self,
        local_log: list[dict[str, Any]],
        candidate_log: list[dict[str, Any]],
        commit_index: int,
    ) -> bool:
        if commit_index < 0:
            return True
        if commit_index >= len(local_log) or commit_index >= len(candidate_log):
            return False
        for idx in range(commit_index + 1):
            if local_log[idx].get("term") != candidate_log[idx].get("term"):
                return False
        return True

    def commit_index_valid(self, commit_index: int, local_log: list[dict[str, Any]]) -> bool:
        return commit_index <= (len(local_log) - 1)

    def roughly_matches_leader(
        self,
        local_log: list[dict[str, Any]],
        leader_log: list[dict[str, Any]],
        tolerance: int = 2,
    ) -> bool:
        if not leader_log:
            return True
        delta = abs(len(leader_log) - len(local_log))
        return delta <= tolerance

    def hash_matches_leader(
        self,
        local_log: list[dict[str, Any]],
        leader_log: list[dict[str, Any]],
    ) -> bool:
        upto = min(len(local_log), len(leader_log))
        for idx in range(upto):
            leader_idx = max(0, idx - 1)
            if _entry_hash(local_log[idx]) != _entry_hash(leader_log[leader_idx]):
                return False
        return True