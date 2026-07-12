"""Job request/response schemas (story B1)."""
from pydantic import BaseModel, ConfigDict, Field, field_validator

from api.config import settings


class JobSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    image: str = Field(min_length=1)
    command: list[str] = Field(min_length=1)
    env: dict[str, str] = Field(default_factory=dict)
    gpu: bool = False
    timeout_minutes: int = Field(default=60, ge=1, le=720)

    @field_validator("command")
    @classmethod
    def validate_command_is_argv(cls, command: list[str]) -> list[str]:
        if not all(isinstance(part, str) and part for part in command):
            raise ValueError("command must be a non-empty list of non-empty strings")
        return command

    @field_validator("image")
    @classmethod
    def validate_allowed_image(cls, image: str) -> str:
        if not any(image.startswith(prefix) for prefix in settings.image_prefixes()):
            allowed = ", ".join(settings.image_prefixes())
            raise ValueError(f"image must start with one of: {allowed}")
        return image


class SubmitJobRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=128)
    spec: JobSpec
