"""Job control channel helpers (story B5)."""
import json

CONTROL_CHANNEL_SUFFIX = ":control"
CANCEL_COMMAND = "cancel"


def job_control_channel(job_id: str) -> str:
    return f"perzforge:jobs:{job_id}{CONTROL_CHANNEL_SUFFIX}"


def cancel_command_message() -> str:
    return json.dumps({"cmd": CANCEL_COMMAND})


def parse_cancel_command(payload: str) -> bool:
    try:
        data = json.loads(payload)
    except json.JSONDecodeError:
        return False
    return isinstance(data, dict) and data.get("cmd") == CANCEL_COMMAND
