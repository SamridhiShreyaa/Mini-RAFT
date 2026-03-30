import random
import time
from typing import Tuple


class ElectionTimer:
    def __init__(self, timeout_range: Tuple[float, float] = (0.5, 0.8)) -> None:
        self.timeout_range = timeout_range
        self.reset()

    def reset(self) -> None:
        self.timeout = random.uniform(*self.timeout_range)
        self.start_time = time.time()

    def expired(self) -> bool:
        return (time.time() - self.start_time) >= self.timeout
