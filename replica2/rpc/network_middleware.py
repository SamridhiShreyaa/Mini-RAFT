import asyncio
import random
from collections import deque
from typing import Any, Awaitable, Callable


RpcFn = Callable[..., Awaitable[Any]]


class NetworkMiddleware:
    def __init__(
        self,
        drop_rate: float = 0.08,
        max_delay_ms: int = 180,
        reorder_rate: float = 0.15,
    ) -> None:
        self.drop_rate = drop_rate
        self.max_delay_ms = max_delay_ms
        self.reorder_rate = reorder_rate
        self._buffer: deque[tuple[RpcFn, tuple[Any, ...], dict[str, Any]]] = deque()

    async def send(self, rpc_call: RpcFn, *args: Any, **kwargs: Any) -> Any:
        if random.random() < self.drop_rate:
            return {"ok": False, "dropped": True}

        delay = random.randint(0, self.max_delay_ms) / 1000.0
        if delay > 0:
            await asyncio.sleep(delay)

        if random.random() < self.reorder_rate:
            self._buffer.append((rpc_call, args, kwargs))
            if len(self._buffer) > 1:
                buffered_call, buffered_args, buffered_kwargs = self._buffer.popleft()
                return await buffered_call(*buffered_args, **buffered_kwargs)

        return await rpc_call(*args, **kwargs)