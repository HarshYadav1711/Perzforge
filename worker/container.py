"""Docker container execution for worker jobs (story B3/B5)."""
import threading
import time
from dataclasses import dataclass

import docker
from docker.errors import APIError, ImageNotFound
from docker.types import DeviceRequest, Mount
from pydantic import ValidationError

from api.config import settings
from api.schemas.job import JobSpec
from worker.logs import LogCollector


@dataclass(frozen=True, slots=True)
class ContainerRunResult:
    exit_code: int | None
    error_message: str | None
    log_tail: str
    timed_out: bool = False
    cancelled: bool = False


def _validate_spec(spec: JobSpec) -> JobSpec:
    return JobSpec.model_validate(spec.model_dump())


def _cleanup_container(client: docker.DockerClient, container_id: str, volume_name: str) -> None:
    try:
        container = client.containers.get(container_id)
        container.remove(force=True)
    except APIError:
        pass

    try:
        client.volumes.get(volume_name).remove(force=True)
    except APIError:
        pass


def run_container(
    spec: JobSpec,
    job_id: str,
    timeout_seconds: int,
    cancel_event: threading.Event | None = None,
) -> ContainerRunResult:
    """Run a job container with hardened defaults. Synchronous — call via asyncio.to_thread."""
    try:
        validated = _validate_spec(spec)
    except ValidationError as exc:
        return ContainerRunResult(
            exit_code=None,
            error_message=f"invalid job spec: {exc.errors()[0]['msg']}",
            log_tail="",
        )

    client = docker.from_env()
    volume_name = f"perzforge-job-{job_id}"
    collector = LogCollector(job_id)
    container = None

    run_kwargs: dict = {
        "image": validated.image,
        "command": validated.command,
        "environment": validated.env,
        "user": "1000:1000",
        "cap_drop": ["ALL"],
        "security_opt": ["no-new-privileges"],
        "network_mode": "none",
        "mem_limit": "6g",
        "nano_cpus": int(4e9),
        "pids_limit": 256,
        "read_only": True,
        "tmpfs": {"/tmp": "size=1g"},
        "mounts": [
            Mount(
                target="/workspace",
                source=volume_name,
                type="volume",
                read_only=False,
            )
        ],
        "working_dir": "/workspace",
        "detach": True,
        "stdout": True,
        "stderr": True,
    }
    if validated.gpu:
        run_kwargs["device_requests"] = [
            DeviceRequest(count=-1, capabilities=[["gpu"]])
        ]

    try:
        try:
            client.images.get(validated.image)
        except ImageNotFound:
            client.images.pull(validated.image)

        container = client.containers.run(**run_kwargs)
        stop_logs = threading.Event()
        log_thread = threading.Thread(
            target=_follow_logs,
            args=(container, collector, stop_logs),
            daemon=True,
        )
        log_thread.start()
        try:
            exit_result = _wait_for_container(
                container,
                timeout_seconds,
                cancel_event,
            )
            if isinstance(exit_result, ContainerRunResult):
                stop_logs.set()
                log_thread.join(timeout=5)
                collector.flush()
                return ContainerRunResult(
                    exit_code=exit_result.exit_code,
                    error_message=exit_result.error_message,
                    log_tail=collector.tail(),
                    timed_out=exit_result.timed_out,
                    cancelled=exit_result.cancelled,
                )

            stop_logs.set()
            log_thread.join(timeout=5)
            collector.flush()
            exit_code = int(exit_result.get("StatusCode", 1))
            return ContainerRunResult(
                exit_code=exit_code,
                error_message=None,
                log_tail=collector.tail(),
            )
        finally:
            stop_logs.set()
            log_thread.join(timeout=2)
    except ImageNotFound:
        return ContainerRunResult(
            exit_code=None,
            error_message=f"image not found: {validated.image}",
            log_tail=collector.tail(),
        )
    except APIError as exc:
        return ContainerRunResult(
            exit_code=None,
            error_message=str(exc),
            log_tail=collector.tail(),
        )
    finally:
        if container is not None:
            _cleanup_container(client, container.id, volume_name)


def _wait_for_container(
    container,
    timeout_seconds: int,
    cancel_event: threading.Event | None,
) -> dict | ContainerRunResult:
    deadline = time.monotonic() + timeout_seconds
    while True:
        if cancel_event is not None and cancel_event.is_set():
            return _stop_container_cancelled(container)

        remaining = deadline - time.monotonic()
        if remaining <= 0:
            container.stop(timeout=10)
            try:
                container.kill()
            except APIError:
                pass
            return ContainerRunResult(
                exit_code=None,
                error_message="timeout",
                log_tail="",
                timed_out=True,
            )

        wait_seconds = min(1.0, remaining)
        container.reload()
        if container.status != "running":
            return container.wait(condition="not-running", timeout=1)

        time.sleep(wait_seconds)


def _stop_container_cancelled(container) -> ContainerRunResult:
    container.stop(timeout=10)
    try:
        container.wait(condition="not-running", timeout=12)
    except Exception:
        try:
            container.kill()
        except APIError:
            pass
    return ContainerRunResult(
        exit_code=None,
        error_message=None,
        log_tail="",
        cancelled=True,
    )


def _follow_logs(container, collector: LogCollector, stop_event: threading.Event) -> None:
    try:
        for chunk in container.logs(stream=True, follow=True):
            if stop_event.is_set():
                break
            text = chunk.decode("utf-8", errors="replace")
            collector.append(text)
    except APIError:
        return


def _collect_logs(container, collector: LogCollector) -> None:
    try:
        raw = container.logs(stdout=True, stderr=True, tail=settings.job_log_tail_lines)
        text = raw.decode("utf-8", errors="replace")
        for line in text.splitlines(keepends=True):
            collector.append(line)
    except APIError:
        return
