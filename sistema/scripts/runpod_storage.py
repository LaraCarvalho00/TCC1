"""Private S3-compatible storage shared by the Runpod worker and its controller."""
from __future__ import annotations

import hashlib
import json
import os

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

PREFIX = "tcc-runpod/"


def missing(error: ClientError) -> bool:
    return error.response["Error"]["Code"] in {"404", "NoSuchKey", "NotFound"}


class RunStorage:
    def __init__(self):
        values = {key: os.environ[key] for key in ("TCC_S3_ENDPOINT", "TCC_S3_BUCKET",
                                                   "TCC_S3_ACCESS_KEY", "TCC_S3_SECRET_KEY")}
        if any(not value or value.startswith("{{") for value in values.values()):
            raise ValueError("Variáveis ou Secrets do bucket de resultados ausentes.")
        self.bucket = values["TCC_S3_BUCKET"]
        self.client = boto3.client(
            "s3", endpoint_url=values["TCC_S3_ENDPOINT"],
            region_name=os.environ.get("TCC_S3_REGION", "auto"),
            aws_access_key_id=values["TCC_S3_ACCESS_KEY"],
            aws_secret_access_key=values["TCC_S3_SECRET_KEY"],
            config=Config(connect_timeout=5, read_timeout=15, retries={"total_max_attempts": 3},
                          request_checksum_calculation="when_required",
                          response_checksum_validation="when_required",
                          s3={"addressing_style": "path"}),
        )

    def put_json(self, key, data, **options):
        self.client.put_object(Bucket=self.bucket, Key=PREFIX + key, Body=json.dumps(data).encode(),
                               ContentType="application/json", **options)

    def get_json(self, key):
        try:
            body = self.client.get_object(Bucket=self.bucket, Key=PREFIX + key)["Body"]
        except ClientError as error:
            if missing(error):
                return None
            raise
        with body:
            return json.load(body)

    def keys(self, prefix):
        for page in self.client.get_paginator("list_objects_v2").paginate(
                Bucket=self.bucket, Prefix=PREFIX + prefix):
            for obj in page.get("Contents", []):
                yield obj["Key"].removeprefix(PREFIX)

    def upload(self, key, path):
        with path.open("rb") as body:
            digest = hashlib.file_digest(body, "sha256").hexdigest()
        self.client.upload_file(str(path), self.bucket, PREFIX + key,
                                ExtraArgs={"Metadata": {"sha256": digest}})
        remote = self.client.head_object(Bucket=self.bucket, Key=PREFIX + key)
        if remote["ContentLength"] != path.stat().st_size or remote["Metadata"].get("sha256") != digest:
            raise RuntimeError("O arquivo enviado não passou na verificação do bucket.")
        return {"key": PREFIX + key, "sha256": digest, "bytes": remote["ContentLength"]}
