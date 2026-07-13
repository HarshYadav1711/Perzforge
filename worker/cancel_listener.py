"""Listen for per-job cancel commands on Redis pub/sub (story B5)."""
import threading

from redis.asyncio import Redis

from api.job_control import job_control_channel, parse_cancel_command


async def watch_for_cancel(redis: Redis, job_id: str, cancel_event: threading.Event) -> None:
    pubsub = redis.pubsub()
    channel = job_control_channel(job_id)
    await pubsub.subscribe(channel)
    try:
        while not cancel_event.is_set():
            message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
            if message is None:
                continue
            if message.get("type") != "message":
                continue
            payload = message.get("data")
            if not isinstance(payload, str):
                payload = str(payload)
            if parse_cancel_command(payload):
                cancel_event.set()
                return
    finally:
        await pubsub.unsubscribe(channel)
        await pubsub.aclose()
