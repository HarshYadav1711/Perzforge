"""Best-effort MLflow run lookup after a job finishes (story B4)."""
from __future__ import annotations

import logging

import httpx

from api.config import settings

logger = logging.getLogger(__name__)

JOB_ID_TAG = "job_id"


def lookup_mlflow_run_id(*, experiment_name: str, job_id: str) -> str | None:
    """Find a run tagged with job_id under the named experiment. Never raises."""
    base = settings.mlflow_tracking_uri.rstrip("/")
    if not base:
        return None

    try:
        with httpx.Client(timeout=5.0) as client:
            exp_resp = client.get(
                f"{base}/api/2.0/mlflow/experiments/get-by-name",
                params={"experiment_name": experiment_name},
            )
            if exp_resp.status_code != 200:
                return None
            experiment_id = exp_resp.json().get("experiment", {}).get("experiment_id")
            if not experiment_id:
                return None

            search_resp = client.post(
                f"{base}/api/2.0/mlflow/runs/search",
                json={
                    "experiment_ids": [str(experiment_id)],
                    "filter": f'tags.`{JOB_ID_TAG}` = "{job_id}"',
                    "max_results": 1,
                    "order_by": ["start_time DESC"],
                },
            )
            if search_resp.status_code != 200:
                return None
            runs = search_resp.json().get("runs") or []
            if not runs:
                return None
            return runs[0].get("info", {}).get("run_id")
    except Exception:
        logger.debug("mlflow run lookup failed for job %s", job_id, exc_info=True)
        return None
