"""Log capture helpers for the worker agent (story B3).

Live streaming to Redis pub/sub is implemented in story B2.
"""
from collections import deque

from api.config import settings


def publish_line(job_id: str, line: str) -> None:
    """B2 seam: stream a single log line to subscribers."""
    _ = (job_id, line)


class LogCollector:
    def __init__(self, job_id: str, max_lines: int | None = None) -> None:
        self._job_id = job_id
        self._lines: deque[str] = deque(maxlen=max_lines or settings.job_log_tail_lines)

    def append(self, line: str) -> None:
        publish_line(self._job_id, line)
        self._lines.append(line)

    def tail(self) -> str:
        return "".join(self._lines)
