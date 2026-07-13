"""Log capture helpers for the worker agent (story B3/B2)."""
from collections import deque

import redis

from api.config import settings
from api.log_stream import eof_cancelled_message, eof_message, job_log_buffer_key, job_log_channel

_sync_redis: redis.Redis | None = None


def _get_sync_redis() -> redis.Redis:
    global _sync_redis
    if _sync_redis is None:
        _sync_redis = redis.from_url(settings.redis_url, decode_responses=True)
    return _sync_redis


def set_sync_redis_client(client: redis.Redis | None) -> None:
    global _sync_redis
    _sync_redis = client


def publish_line(job_id: str, line: str) -> None:
    """Publish a log line to Redis pub/sub and the capped replay buffer."""
    client = _get_sync_redis()
    channel = job_log_channel(job_id)
    buffer_key = job_log_buffer_key(job_id)
    client.publish(channel, line)
    client.rpush(buffer_key, line)
    client.ltrim(buffer_key, -settings.job_log_replay_max_lines, -1)


def publish_eof_cancelled(job_id: str) -> None:
    """Signal cancelled stream end to live subscribers."""
    payload = eof_cancelled_message()
    client = _get_sync_redis()
    channel = job_log_channel(job_id)
    buffer_key = job_log_buffer_key(job_id)
    client.publish(channel, payload)
    client.rpush(buffer_key, payload)
    client.ltrim(buffer_key, -settings.job_log_replay_max_lines, -1)


def publish_eof(job_id: str, exit_code: int | None) -> None:
    """Signal stream end to live subscribers and append eof to replay buffer."""
    payload = eof_message(exit_code)
    client = _get_sync_redis()
    channel = job_log_channel(job_id)
    buffer_key = job_log_buffer_key(job_id)
    client.publish(channel, payload)
    client.rpush(buffer_key, payload)
    client.ltrim(buffer_key, -settings.job_log_replay_max_lines, -1)


class LogCollector:
    def __init__(self, job_id: str, max_lines: int | None = None) -> None:
        self._job_id = job_id
        self._lines: deque[str] = deque(maxlen=max_lines or settings.job_log_tail_lines)
        self._partial = ""

    def append(self, chunk: str) -> None:
        self._partial += chunk
        while "\n" in self._partial:
            line, self._partial = self._partial.split("\n", 1)
            full_line = f"{line}\n"
            publish_line(self._job_id, full_line)
            self._lines.append(full_line)

    def flush(self) -> None:
        if not self._partial:
            return
        publish_line(self._job_id, self._partial)
        self._lines.append(self._partial)
        self._partial = ""

    def tail(self) -> str:
        self.flush()
        return "".join(self._lines)
