import boto3, base64, hashlib
from botocore.client import Config
from ..config import settings

_s3 = boto3.client(
    "s3",
    endpoint_url=settings.S3_ENDPOINT,
    aws_access_key_id=settings.S3_ACCESS_KEY,
    aws_secret_access_key=settings.S3_SECRET_KEY,
    config=Config(signature_version="s3v4"),
    region_name="us-east-1"
)

def put_bytes(key: str, data: bytes, mime: str):
    _s3.put_object(Bucket=settings.S3_BUCKET, Key=key, Body=data, ContentType=mime)

def get_bytes(key: str) -> bytes:
    obj = _s3.get_object(Bucket=settings.S3_BUCKET, Key=key)
    return obj["Body"].read()
