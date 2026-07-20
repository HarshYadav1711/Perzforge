"""Endpoint request/response schemas (story C1)."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, RootModel

from api.models import EndpointStatus


class DeployRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=128)


class EndpointResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: uuid.UUID
    model_id: uuid.UUID
    name: str
    status: EndpointStatus
    route: str
    container_id: str | None
    error_message: str | None
    created_at: datetime
    stopped_at: datetime | None


class EndpointListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[EndpointResponse]
    total: int
    limit: int
    offset: int


class PredictRequest(RootModel[dict[str, Any]]):
    """Opaque JSON object forwarded to the runner's predict().

    RootModel rejects non-object JSON at the boundary; open object keys are intentional
    (serving contract is user-defined).
    """
