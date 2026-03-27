import asyncio
from typing import Any

import requests


class ReconciliationEngine:
    def __init__(self, memory_log: list[dict[str, Any]]) -> None:
        self.memory_log = memory_log

    async def fetch_from_leader(self, leader_url: str, from_index: int) -> list[dict[str, Any]]:
        def _fetch() -> list[dict[str, Any]]:
            res = requests.post(
                f"{leader_url}/sync-log",
                json={"from_index": from_index},
                timeout=1.0,
            )
            if not res.ok:
                return []
            data = res.json()
            return data.get("entries", [])

        return await asyncio.to_thread(_fetch)

    async def reconcile(self, leader_url: str, conflict_index: int) -> int:
        if conflict_index < len(self.memory_log):
            del self.memory_log[conflict_index:]

        incoming = await self.fetch_from_leader(leader_url, conflict_index)
        for item in incoming:
            self.memory_log.append(item)
        return len(incoming)