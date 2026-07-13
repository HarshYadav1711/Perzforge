"""WebSocket log relay with backpressure thinning (story B2)."""
import asyncio
import json
from typing import Any

from fastapi import WebSocket
from redis.asyncio import Redis

from api.config import settings
from api.log_stream import (
    job_log_buffer_key,
    job_log_channel,
    parse_stream_payload,
    replay_buffer_max_index,
)


class LogWebSocketRelay:
    def __init__(self, websocket: WebSocket) -> None:
        self._websocket = websocket
        self._thin_mode = False
        self._thin_marker_sent = False
        self._skipped = 0

    async def send_line(self, line: str) -> None:
        if self._thin_mode:
            self._skipped += 1
            if self._skipped % settings.job_log_ws_thin_interval != 0:
                return
            if not self._thin_marker_sent:
                await self._websocket.send_text("[stream thinned]\n")
                self._thin_marker_sent = True

        try:
            await asyncio.wait_for(
                self._websocket.send_text(line),
                timeout=settings.job_log_ws_send_timeout_seconds,
            )
        except TimeoutError:
            self._thin_mode = True
            self._skipped = 0
            await self.send_line(line)

    async def replay_buffer(self, redis: Redis, job_id: str) -> None:
        buffer_key = job_log_buffer_key(job_id)
        lines = await redis.lrange(buffer_key, 0, replay_buffer_max_index())
        for line in lines:
            payload, eof = parse_stream_payload(line)
            if eof is not None:
                return
            if payload is not None:
                await self.send_line(payload)

    async def relay_live(self, redis: Redis, job_id: str) -> dict[str, Any] | None:
        pubsub = redis.pubsub()
        await pubsub.subscribe(job_log_channel(job_id))
        try:
            while True:
                message = await pubsub.get_message(
                    ignore_subscribe_messages=True,
                    timeout=1.0,
                )
                if message is None:
                    continue
                if message.get("type") != "message":
                    continue

                payload = message.get("data")
                if not isinstance(payload, str):
                    payload = str(payload)

                line, eof = parse_stream_payload(payload)
                if eof is not None:
                    return eof
                if line is not None:
                    await self.send_line(line)
        finally:
            await pubsub.unsubscribe(job_log_channel(job_id))
            await pubsub.aclose()

    async def send_eof(self, eof: dict[str, Any]) -> None:
        await self._websocket.send_text(json.dumps(eof))
