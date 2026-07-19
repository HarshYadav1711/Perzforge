"""Model registry request/response schemas (story B4)."""
import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ModelResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: uuid.UUID
    name: str
    version: int
    source_job_id: uuid.UUID | None
    minio_prefix: str
    size_bytes: int
    framework: str | None
    created_at: datetime


class ModelListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[ModelResponse]
    total: int
    limit: int
    offset: int


class PresignedFile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: str
    url: str
    size: int = Field(ge=0)


class ModelDownloadResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    files: list[PresignedFile]
    expires_in: int
