from typing import Any

from replica.log.commitManager import CommitManager


class ReplicationSafety:
    def __init__(self, commit_manager: CommitManager) -> None:
        self.commit_manager = commit_manager

    def majority_commit_index(self) -> int:
        return self.commit_manager.get_commit_index()

    def never_overwrite_committed(
        self,
        local_log: list[dict[str, Any]],
        incoming_log: list[dict[str, Any]],
        commit_index: int,
    ) -> bool:
        if commit_index < 0:
            return True
        if len(local_log) <= commit_index or len(incoming_log) <= commit_index:
            return False
        for idx in range(commit_index + 1):
            if local_log[idx].get("term") != incoming_log[idx].get("term"):
                return False
        return True

    def apply_only_committed(
        self,
        local_log: list[dict[str, Any]],
        last_applied: int,
        commit_index: int,
    ) -> tuple[int, list[dict[str, Any]]]:
        if commit_index <= last_applied:
            return last_applied, []
        upper = min(commit_index, len(local_log) - 1)
        if upper < 0:
            return last_applied, []
        to_apply = local_log[last_applied + 1 : upper + 1]
        return upper, to_apply