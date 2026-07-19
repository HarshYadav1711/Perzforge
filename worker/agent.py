"""Perzforge worker agent — executes queued jobs in hardened Docker containers."""
import asyncio
import contextlib
import logging
import shutil
import socket
import threading
import uuid

from redis.asyncio import Redis
from redis.exceptions import TimeoutError as RedisTimeoutError

from api.config import settings
from api.models import JobStatus
from api.queue import JOB_QUEUE_KEY
from api.schemas.job import JobSpec
from api.storage import get_storage
from worker.artifacts import promote_outputs
from worker.cancel_listener import watch_for_cancel
from worker.container import ContainerRunResult, run_container
from worker.lock import WorkerLock
from worker.logs import publish_eof, publish_eof_cancelled
from worker.mlflow_lookup import lookup_mlflow_run_id
from worker.repository import finalize_job, load_job, mark_job_running, reap_zombie_jobs

logger = logging.getLogger(__name__)


def _worker_redis() -> Redis:
    # BRPOP blocks up to worker_brpop_timeout_seconds; socket read must outlive that wait.
    return Redis.from_url(
        settings.redis_url,
        decode_responses=True,
        socket_timeout=settings.worker_brpop_timeout_seconds + 5,
    )


async def process_job(job_id: str, worker_hostname: str, redis: Redis) -> None:
    try:
        job_uuid = uuid.UUID(job_id)
    except ValueError:
        logger.warning("invalid job id from queue: %s", job_id)
        return

    job = await load_job(job_uuid)
    if job is None or job.status != JobStatus.QUEUED:
        return

    try:
        spec = JobSpec.model_validate(job.spec)
    except Exception as exc:
        await finalize_job(
            job_uuid,
            status=JobStatus.FAILED,
            exit_code=None,
            error_message=f"invalid job spec: {exc}",
            log_tail="",
        )
        return

    running_job = await mark_job_running(job_uuid, worker_hostname)
    if running_job is None:
        return

    cancel_event = threading.Event()
    watch_task = asyncio.create_task(watch_for_cancel(redis, job_id, cancel_event))
    try:
        result = await asyncio.to_thread(
            run_container,
            spec,
            job_id,
            spec.timeout_minutes * 60,
            cancel_event,
            job_name=running_job.name,
        )
    finally:
        cancel_event.set()
        watch_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await watch_task

    await _apply_container_result(job_uuid, running_job.user_id, running_job.name, result, redis)


async def _apply_container_result(
    job_id: uuid.UUID,
    user_id: uuid.UUID,
    job_name: str,
    result: ContainerRunResult,
    redis: Redis,
) -> None:
    try:
        if result.cancelled:
            await finalize_job(
                job_id,
                status=JobStatus.CANCELLED,
                exit_code=None,
                error_message=None,
                log_tail=result.log_tail,
            )
            publish_eof_cancelled(str(job_id))
            return

        if result.timed_out or result.error_message == "timeout":
            status = JobStatus.FAILED
            error_message = "timeout"
            exit_code = result.exit_code
        elif result.error_message is not None:
            status = JobStatus.FAILED
            error_message = result.error_message
            exit_code = result.exit_code
        elif result.exit_code == 0:
            status = JobStatus.SUCCEEDED
            error_message = None
            exit_code = 0
        else:
            status = JobStatus.FAILED
            error_message = None
            exit_code = result.exit_code

        artifact_error: str | None = None
        log_tail = result.log_tail
        if status == JobStatus.SUCCEEDED and result.outputs_dir is not None:
            try:
                _model, artifact_error = await promote_outputs(
                    job_id=job_id,
                    user_id=user_id,
                    job_name=job_name,
                    outputs_dir=result.outputs_dir,
                    redis=redis,
                    storage=get_storage(),
                )
            except Exception as exc:
                logger.exception("artifact promotion failed for job %s", job_id)
                artifact_error = f"artifact upload failed: {exc}"

            if artifact_error:
                log_tail = f"{log_tail}{artifact_error}\n"

        mlflow_run_id = None
        if status == JobStatus.SUCCEEDED:
            try:
                mlflow_run_id = lookup_mlflow_run_id(
                    experiment_name=job_name,
                    job_id=str(job_id),
                )
            except Exception:
                logger.debug("mlflow lookup raised for job %s", job_id, exc_info=True)

        await finalize_job(
            job_id,
            status=status,
            exit_code=exit_code,
            error_message=error_message,
            log_tail=log_tail,
            mlflow_run_id=mlflow_run_id,
            artifact_error=artifact_error,
        )
        publish_eof(str(job_id), exit_code)
    finally:
        if result.outputs_dir is not None:
            shutil.rmtree(result.outputs_dir, ignore_errors=True)


async def run_loop(redis: Redis, worker_hostname: str) -> None:
    lock = WorkerLock(redis, worker_hostname)
    if not await lock.acquire():
        logger.error("another worker agent already holds the lock on %s", worker_hostname)
        return

    reaped = await reap_zombie_jobs(worker_hostname)
    if reaped:
        logger.warning("reaped %s zombie RUNNING jobs for %s", reaped, worker_hostname)

    logger.info("worker agent started on %s — waiting for jobs on %s", worker_hostname, JOB_QUEUE_KEY)

    try:
        while True:
            if not await lock.refresh():
                logger.error("lost worker lock — stopping agent")
                break

            try:
                item = await redis.brpop(
                    JOB_QUEUE_KEY,
                    timeout=settings.worker_brpop_timeout_seconds,
                )
            except RedisTimeoutError:
                continue
            except asyncio.CancelledError:
                logger.info("worker agent shutting down")
                break
            if item is None:
                continue

            _, queued_job_id = item
            await process_job(queued_job_id, worker_hostname, redis)
    finally:
        await lock.release()


async def _async_main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    hostname = socket.gethostname()
    redis = _worker_redis()
    try:
        await run_loop(redis, hostname)
    finally:
        await redis.aclose()


def main() -> None:
    try:
        asyncio.run(_async_main())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
