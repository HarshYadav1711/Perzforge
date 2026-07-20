"""Minimal runner that loads /model/serve.py and exposes /healthz + /predict."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any, Callable

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, ConfigDict, RootModel

MODEL_DIR = Path("/model")
SERVE_PATH = MODEL_DIR / "serve.py"


def _load_predict() -> Callable[[dict[str, Any]], dict[str, Any]]:
    if not SERVE_PATH.is_file():
        raise RuntimeError(f"serving contract violation: {SERVE_PATH} not found")

    sys.path.insert(0, str(MODEL_DIR))
    spec = importlib.util.spec_from_file_location("perzforge_serve", SERVE_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("failed to load serve.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    predict_fn = getattr(module, "predict", None)
    if not callable(predict_fn):
        raise RuntimeError("serving contract violation: serve.py must define predict(payload: dict) -> dict")
    return predict_fn  # type: ignore[return-value]


class PredictBody(RootModel[dict[str, Any]]):
    pass


class HealthResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: str


app = FastAPI(title="perzforge-serve-runner", docs_url=None, redoc_url=None)
_predict = _load_predict()


@app.get("/healthz", response_model=HealthResponse)
def healthz() -> HealthResponse:
    return HealthResponse(status="ok")


@app.post("/predict")
def predict(body: PredictBody) -> dict[str, Any]:
    try:
        result = _predict(body.root)
    except Exception as exc:  # noqa: BLE001 — surface model errors as 500
        raise HTTPException(status_code=500, detail=f"predict failed: {exc}") from exc
    if not isinstance(result, dict):
        raise HTTPException(
            status_code=500,
            detail="predict must return a dict",
        )
    return result
