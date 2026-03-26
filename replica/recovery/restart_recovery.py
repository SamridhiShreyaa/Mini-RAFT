from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any


@dataclass
class RecoveryState:
    commit_index: int = -1
    last_applied: int = -1


class RecoveryLayer:
    def __init__(self, node_id: str, disk_dir: str = "logs") -> None:
        self.node_id = node_id
        self.disk_dir = Path(disk_dir)
        self.state = RecoveryState()
        self.memory_log: list[dict[str, Any]] = []
        self.disk_dir.mkdir(parents=True, exist_ok=True)

    def _disk_path(self) -> Path:
        return self.disk_dir / f"node_{self.node_id}.json"

    def _restore_indices(self) -> None:
        committed = [e["index"] for e in self.memory_log if e.get("is_committed")]
        if committed:
            self.state.commit_index = max(committed)
            self.state.last_applied = self.state.commit_index
            return

        if self.memory_log:
            self.state.commit_index = -1
            self.state.last_applied = min(len(self.memory_log) - 1, 0)
            return

        self.state.commit_index = -1
        self.state.last_applied = -1

    def load_logs(self) -> list[dict[str, Any]]:
        path = self._disk_path()
        loaded: list[dict[str, Any]] = []
        if path.exists():
            for line in path.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                try:
                    loaded.append(json.loads(line))
                except Exception:
                    continue
        self.memory_log = loaded
        return loaded

    async def bootstrap(self) -> RecoveryState:
        self.load_logs()
        self._restore_indices()
        return self.state