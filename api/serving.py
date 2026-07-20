"""Model endpoint serving: artifact fetch, runner containers, health, reconcile (story C1)."""
from __future__ import annotations

import asyncio
import logging
import re
import shutil
import time
import uuid
from pathlib import Path

import docker
import httpx
from docker.errors import APIError, ImageNotFound, NotFound
from docker.types import Mount
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.config import settings
from api.models import Endpoint, EndpointStatus, Model
from api.storage import ObjectStorage, get_storage

logger = logging.getLogger(__name__)

SERVE_PY = "serve.py"
ACTIVE_ENDPOINT_STATUSES = (EndpointStatus.STARTING, EndpointStatus.LIVE)


class ServingError(Exception):
    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)


def make_route(name: str, endpoint_id: uuid.UUID) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:48] or "model"
    return f"{base}-{endpoint_id.hex[:8]}"


def artifact_dir_for(endpoint_id: uuid.UUID) -> Path:
    return Path(settings.serving_artifact_root) / str(endpoint_id)


def ensure_serving_network(client: docker.DockerClient | None = None) -> None:
    docker_client = client or docker.from_env()
    name = settings.serving_network_name
    try:
        docker_client.networks.get(name)
    except NotFound:
        docker_client.networks.create(name, driver="bridge", check_duplicate=True)


def download_model_artifacts(storage: ObjectStorage, model: Model, dest: Path) -> None:
    if dest.exists():
        shutil.rmtree(dest, ignore_errors=True)
    dest.mkdir(parents=True, exist_ok=True)
    count = storage.download_prefix(model.minio_prefix, dest)
    if count == 0:
        raise ServingError("model artifact prefix is empty")
    if not (dest / SERVE_PY).is_file():
        raise ServingError(
            f"serving contract violation: {SERVE_PY} missing from artifact prefix"
        )


def start_runner_container(endpoint_id: uuid.UUID, artifact_dir: Path) -> str:
    """Start hardened serve-runner. Returns Docker container id. Sync — use to_thread."""
    client = docker.from_env()
    ensure_serving_network(client)
    image = settings.serve_runner_image
    container_name = f"perzforge-endpoint-{endpoint_id}"

    try:
        existing = client.containers.get(container_name)
        existing.remove(force=True)
    except NotFound:
        pass

    try:
        client.images.get(image)
    except ImageNotFound:
        try:
            client.images.pull(image)
        except APIError as exc:
            raise ServingError(f"serve runner image unavailable: {image}") from exc

    port = settings.serving_container_port
    run_kwargs: dict = {
        "image": image,
        "name": container_name,
        "user": "1000:1000",
        "cap_drop": ["ALL"],
        "security_opt": ["no-new-privileges"],
        "mem_limit": "2g",
        "nano_cpus": int(2e9),
        "pids_limit": 128,
        "read_only": True,
        "tmpfs": {"/tmp": "size=512m"},
        "mounts": [
            Mount(
                target="/model",
                source=str(artifact_dir.resolve()),
                type="bind",
                read_only=True,
            )
        ],
        "network": settings.serving_network_name,
        "ports": {f"{port}/tcp": None},
        "detach": True,
        "stdout": True,
        "stderr": True,
    }

    try:
        container = client.containers.run(**run_kwargs)
    except APIError as exc:
        raise ServingError(f"failed to start runner: {exc}") from exc
    return container.id


def stop_runner_container(container_id: str) -> None:
    """Stop and remove a runner container. Sync — use to_thread."""
    if not container_id:
        return
    client = docker.from_env()
    try:
        container = client.containers.get(container_id)
        container.remove(force=True)
    except NotFound:
        return
    except APIError as exc:
        logger.warning("failed to remove container %s: %s", container_id, exc)


def container_exists(container_id: str) -> bool:
    if not container_id:
        return False
    client = docker.from_env()
    try:
        client.containers.get(container_id)
        return True
    except NotFound:
        return False
    except APIError:
        return False


def runner_base_url(container_id: str) -> str:
    """Resolve http://host:port for a running runner (published port)."""
    client = docker.from_env()
    try:
        container = client.containers.get(container_id)
    except NotFound as exc:
        raise ServingError("endpoint container not found") from exc

    container.reload()
    port_key = f"{settings.serving_container_port}/tcp"
    ports = (container.attrs.get("NetworkSettings") or {}).get("Ports") or {}
    bindings = ports.get(port_key) or []
    if not bindings:
        raise ServingError("endpoint container has no published port")
    host_port = bindings[0].get("HostPort")
    if not host_port:
        raise ServingError("endpoint container has no host port binding")
    return f"http://127.0.0.1:{host_port}"


def wait_for_health(base_url: str, timeout_seconds: int | None = None) -> None:
    """Poll GET /healthz until 200 or timeout. Sync — use to_thread."""
    deadline = time.monotonic() + (timeout_seconds or settings.serving_health_timeout_seconds)
    health_url = f"{base_url.rstrip('/')}/healthz"
    last_error = "health check did not succeed"
    with httpx.Client(timeout=2.0) as client:
        while time.monotonic() < deadline:
            try:
                response = client.get(health_url)
                if response.status_code == 200:
                    return
                last_error = f"healthz returned {response.status_code}"
            except httpx.HTTPError as exc:
                last_error = str(exc) or exc.__class__.__name__
            time.sleep(0.5)
    raise ServingError(f"endpoint unhealthy within timeout: {last_error}")


def cleanup_artifact_dir(endpoint_id: uuid.UUID) -> None:
    path = artifact_dir_for(endpoint_id)
    if path.exists():
        shutil.rmtree(path, ignore_errors=True)


async def activate_endpoint(
    db: AsyncSession,
    endpoint: Endpoint,
    model: Model,
    storage: ObjectStorage | None = None,
) -> Endpoint:
    """Download artifacts, start runner, health-gate → LIVE or FAILED."""
    store = storage or get_storage()
    artifact_dir = artifact_dir_for(endpoint.id)

    try:
        if not store.prefix_has_file(model.minio_prefix, SERVE_PY):
            raise ServingError(
                f"serving contract violation: {SERVE_PY} missing from artifact prefix"
            )

        await asyncio.to_thread(download_model_artifacts, store, model, artifact_dir)
        container_id = await asyncio.to_thread(start_runner_container, endpoint.id, artifact_dir)
        endpoint.container_id = container_id
        await db.commit()

        base_url = await asyncio.to_thread(runner_base_url, container_id)
        await asyncio.to_thread(wait_for_health, base_url)

        endpoint.status = EndpointStatus.LIVE
        endpoint.error_message = None
        await db.commit()
        return endpoint
    except ServingError as exc:
        return await _mark_failed(db, endpoint, exc.message)
    except Exception as exc:  # noqa: BLE001 — never leave STARTING on unexpected errors
        logger.exception("endpoint activate failed for %s", endpoint.id)
        return await _mark_failed(db, endpoint, str(exc)[:1024])


async def _mark_failed(db: AsyncSession, endpoint: Endpoint, message: str) -> Endpoint:
    if endpoint.container_id:
        await asyncio.to_thread(stop_runner_container, endpoint.container_id)
    await asyncio.to_thread(cleanup_artifact_dir, endpoint.id)
    endpoint.status = EndpointStatus.FAILED
    endpoint.container_id = None
    endpoint.error_message = message[:1024]
    await db.commit()
    return endpoint


async def stop_endpoint_runtime(db: AsyncSession, endpoint: Endpoint) -> Endpoint:
    from datetime import UTC, datetime

    if endpoint.container_id:
        await asyncio.to_thread(stop_runner_container, endpoint.container_id)
    await asyncio.to_thread(cleanup_artifact_dir, endpoint.id)
    endpoint.status = EndpointStatus.STOPPED
    endpoint.container_id = None
    endpoint.stopped_at = datetime.now(UTC)
    endpoint.error_message = None
    await db.commit()
    return endpoint


async def reconcile_vanished_containers(db: AsyncSession) -> int:
    """Mark STARTING/LIVE endpoints whose containers are gone as FAILED. Returns count."""
    result = await db.execute(
        select(Endpoint).where(Endpoint.status.in_(ACTIVE_ENDPOINT_STATUSES))
    )
    endpoints = list(result.scalars().all())
    marked = 0
    for endpoint in endpoints:
        cid = endpoint.container_id
        if cid and await asyncio.to_thread(container_exists, cid):
            continue
        if cid:
            await asyncio.to_thread(stop_runner_container, cid)
        await asyncio.to_thread(cleanup_artifact_dir, endpoint.id)
        endpoint.status = EndpointStatus.FAILED
        endpoint.container_id = None
        endpoint.error_message = "container vanished (reconciled on API startup)"
        marked += 1
    if marked:
        await db.commit()
    return marked
