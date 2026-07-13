"""Redis log streaming helpers (story B2)."""
import json
from typing import Any

from api.config import settings

LOG_CHANNEL_SUFFIX = ":logs"
LOG_BUFFER_SUFFIX = ":logbuf"
EOF_EVENT = "eof"


def job_log_channel(job_id: str) -> str:
    return f"perzforge:jobs:{job_id}{LOG_CHANNEL_SUFFIX}"


def job_log_buffer_key(job_id: str) -> str:
    return f"perzforge:jobs:{job_id}{LOG_BUFFER_SUFFIX}"


def eof_message(exit_code: int | None) -> str:
    return json.dumps({"event": EOF_EVENT, "exit_code": exit_code})


def eof_cancelled_message() -> str:
    return json.dumps({"event": EOF_EVENT, "cancelled": True})


def parse_stream_payload(payload: str) -> tuple[str | None, dict[str, Any] | None]:
    if not payload.startswith("{"):
        return payload, None
    try:
        data = json.loads(payload)
    except json.JSONDecodeError:
        return payload, None
    if isinstance(data, dict) and data.get("event") == EOF_EVENT:
        return None, data
    return payload, None


def replay_buffer_max_index() -> int:
    return settings.job_log_replay_max_lines - 1
