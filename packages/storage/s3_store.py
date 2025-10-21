from __future__ import annotations

from typing import Tuple, Optional
import boto3
from botocore.client import Config
from botocore.exceptions import ClientError


class S3Store:
    """
    Thin S3/MinIO helper.
    - Does NOT raise on init.
    - Bucket checks are explicit with `ensure_bucket`.
    """

    def __init__(
        self,
        *,
        endpoint: str,
        access_key: str,
        secret_key: str,
        bucket: str,
        region: str = "us-east-1",
        address_style: str = "path",  # MinIO-friendly
    ) -> None:
        self.endpoint = endpoint
        self.access_key = access_key
        self.secret_key = secret_key
        self.bucket = bucket
        self.region = region

        self.s3 = boto3.client(
            "s3",
            endpoint_url=self.endpoint,
            aws_access_key_id=self.access_key,
            aws_secret_access_key=self.secret_key,
            region_name=self.region,
            config=Config(signature_version="s3v4", s3={"addressing_style": address_style}),
        )

    # ---------- health / bucket mgmt ----------
    def ensure_bucket(self, create_if_missing: bool = False) -> Tuple[bool, str]:
        try:
            self.s3.head_bucket(Bucket=self.bucket)
            return True, "bucket exists"
        except ClientError as e:
            code = (e.response.get("Error") or {}).get("Code", "")
            if code in {"404", "NoSuchBucket"} and create_if_missing:
                try:
                    # MinIO ignores LocationConstraint for us-east-1
                    kwargs = {"Bucket": self.bucket}
                    if self.region and self.region != "us-east-1":
                        kwargs["CreateBucketConfiguration"] = {"LocationConstraint": self.region}
                    self.s3.create_bucket(**kwargs)
                    return True, "bucket created"
                except ClientError as ce:
                    return False, f"create failed: {ce}"
            return False, f"head failed: {e}"

    # ---------- data ops ----------
    def upload_bytes(self, key: str, data: bytes, *, content_type: str = "application/octet-stream") -> None:
        self.s3.put_object(Bucket=self.bucket, Key=key, Body=data, ContentType=content_type)

    def presign_url(self, key: str, *, expires_seconds: int = 3600) -> str:
        return self.s3.generate_presigned_url(
            "get_object",
            Params={"Bucket": self.bucket, "Key": key},
            ExpiresIn=expires_seconds,
        )
