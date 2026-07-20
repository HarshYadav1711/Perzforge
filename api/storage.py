"""S3-compatible object storage seam (story B4). All MinIO access goes through here."""
from __future__ import annotations

import math
import uuid
from functools import lru_cache
from pathlib import Path
from typing import BinaryIO

import boto3
from botocore.client import Config
from botocore.exceptions import ClientError

from api.config import settings

PRESIGN_EXPIRY_SECONDS = 15 * 60


def user_prefix(user_id: uuid.UUID) -> str:
    return f"users/{user_id}/"


def model_prefix(user_id: uuid.UUID, name: str, version: int) -> str:
    return f"models/{user_id}/{name}/{version}/"


def size_to_storage_mb(size_bytes: int) -> int:
    if size_bytes <= 0:
        return 0
    return max(1, math.ceil(size_bytes / (1024 * 1024)))


class ObjectStorage:
    """Thin boto3 wrapper bound to configured MinIO/S3 settings."""

    def __init__(self) -> None:
        self._bucket = settings.minio_bucket
        self._client = boto3.client(
            "s3",
            endpoint_url=settings.minio_endpoint,
            aws_access_key_id=settings.minio_access_key,
            aws_secret_access_key=settings.minio_secret_key,
            region_name=settings.minio_region,
            config=Config(signature_version="s3v4"),
            use_ssl=settings.minio_secure,
        )

    def ensure_bucket(self) -> None:
        try:
            self._client.head_bucket(Bucket=self._bucket)
        except ClientError:
            self._client.create_bucket(Bucket=self._bucket)

    def put_bytes(self, key: str, data: bytes, content_type: str = "application/octet-stream") -> None:
        self._client.put_object(
            Bucket=self._bucket,
            Key=key,
            Body=data,
            ContentType=content_type,
        )

    def put_file(self, key: str, fileobj: BinaryIO, content_type: str = "application/octet-stream") -> None:
        self._client.upload_fileobj(
            fileobj,
            self._bucket,
            key,
            ExtraArgs={"ContentType": content_type},
        )

    def get_bytes(self, key: str) -> bytes:
        response = self._client.get_object(Bucket=self._bucket, Key=key)
        return response["Body"].read()

    def object_exists(self, key: str) -> bool:
        try:
            self._client.head_object(Bucket=self._bucket, Key=key)
            return True
        except ClientError:
            return False

    def list_keys(self, prefix: str) -> list[str]:
        keys: list[str] = []
        paginator = self._client.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=self._bucket, Prefix=prefix):
            for item in page.get("Contents", []):
                keys.append(item["Key"])
        return keys

    def list_files(self, prefix: str) -> list[dict[str, int | str]]:
        files: list[dict[str, int | str]] = []
        paginator = self._client.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=self._bucket, Prefix=prefix):
            for item in page.get("Contents", []):
                key = item["Key"]
                relative = key[len(prefix) :] if key.startswith(prefix) else key
                if not relative or relative.endswith("/"):
                    continue
                files.append({"key": relative, "size": int(item["Size"]), "full_key": key})
        return files

    def presign_get(self, key: str, expires_in: int = PRESIGN_EXPIRY_SECONDS) -> str:
        return self._client.generate_presigned_url(
            "get_object",
            Params={"Bucket": self._bucket, "Key": key},
            ExpiresIn=expires_in,
        )

    def delete_prefix(self, prefix: str) -> int:
        keys = self.list_keys(prefix)
        deleted = 0
        for offset in range(0, len(keys), 1000):
            chunk = keys[offset : offset + 1000]
            if not chunk:
                continue
            self._client.delete_objects(
                Bucket=self._bucket,
                Delete={"Objects": [{"Key": key} for key in chunk], "Quiet": True},
            )
            deleted += len(chunk)
        return deleted

    def prefix_has_file(self, prefix: str, relative_name: str) -> bool:
        key = f"{prefix}{relative_name}" if prefix.endswith("/") else f"{prefix}/{relative_name}"
        return self.object_exists(key)

    def download_prefix(self, prefix: str, dest: Path) -> int:
        """Download all objects under prefix into dest. Returns file count."""
        dest.mkdir(parents=True, exist_ok=True)
        files = self.list_files(prefix)
        for item in files:
            relative = Path(str(item["key"]))
            # Reject path traversal outside dest
            target = (dest / relative).resolve()
            if not str(target).startswith(str(dest.resolve())):
                raise ValueError(f"refusing path outside destination: {item['key']}")
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(self.get_bytes(str(item["full_key"])))
        return len(files)


@lru_cache(maxsize=1)
def get_storage() -> ObjectStorage:
    storage = ObjectStorage()
    storage.ensure_bucket()
    return storage


def reset_storage_cache() -> None:
    clear = getattr(get_storage, "cache_clear", None)
    if callable(clear):
        clear()
