from dataclasses import dataclass
from typing import Any


@dataclass
class RecoveryState:
    commit_index: int = -1
    last_applied: int = -1


class RecoveryLayer:
    def __init__(self, node_id: str) -> None:
        self.node_id = node_id
        self.state = RecoveryState()
        self.memory_log: list[dict[str, Any]] = []

    async def bootstrap(self) -> RecoveryState:
        return self.state