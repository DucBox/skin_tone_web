"""One immutable record per assessment; no shared index or local Railway disk."""
import json
import os
import re
from pathlib import Path
from uuid import uuid4
from datetime import datetime, timezone


class HistoryStore:
    PREFIX = "skin-tone/history/"

    def __init__(self):
        names = ("S3_BUCKET_NAME", "S3_ENDPOINT_URL", "S3_ACCESS_KEY_ID",
                 "S3_SECRET_ACCESS_KEY", "S3_REGION")
        settings = {name: os.environ.get(name, "").strip() for name in names}
        self.client = None
        self.bucket = settings["S3_BUCKET_NAME"]
        if any(settings.values()):
            if not all(settings.values()):
                raise RuntimeError("Thiếu cấu hình lưu lịch sử.")
            import boto3
            from botocore.config import Config
            self.client = boto3.client(
                "s3", endpoint_url=settings["S3_ENDPOINT_URL"],
                region_name=settings["S3_REGION"],
                aws_access_key_id=settings["S3_ACCESS_KEY_ID"],
                aws_secret_access_key=settings["S3_SECRET_ACCESS_KEY"],
                config=Config(signature_version="s3v4", connect_timeout=10,
                              read_timeout=30, retries={"max_attempts": 2},
                              s3={"addressing_style": os.environ.get("S3_URL_STYLE", "virtual")}),
            )
        elif os.environ.get("RAILWAY_ENVIRONMENT_ID"):
            raise RuntimeError("Chưa cấu hình Bucket để lưu lịch sử.")
        self.root = Path(os.environ.get("HISTORY_DIR", "history_data"))

    @staticmethod
    def validate_id(record_id):
        if not re.fullmatch(r"\d{8}T\d{12}Z-[a-f0-9]{32}", record_id):
            raise ValueError("Invalid history ID")
        return record_id

    def key(self, record_id, name="record.json"):
        return f"{self.PREFIX}{self.validate_id(record_id)}/{name}"

    def put(self, key, data, content_type):
        if self.client:
            self.client.put_object(Bucket=self.bucket, Key=key, Body=data,
                                   ContentType=content_type)
        else:
            target = self.root / key
            target.parent.mkdir(parents=True, exist_ok=True)
            temporary = target.with_name(target.name + "." + uuid4().hex + ".tmp")
            temporary.write_bytes(data)
            temporary.replace(target)

    def read(self, key):
        if self.client:
            try:
                body = self.client.get_object(Bucket=self.bucket, Key=key)["Body"]
            except self.client.exceptions.NoSuchKey:
                raise FileNotFoundError(key)
            try:
                return body.read()
            finally:
                body.close()
        return (self.root / key).read_bytes()

    def remove_keys(self, keys):
        if self.client:
            response = self.client.delete_objects(
                Bucket=self.bucket, Delete={"Objects": [{"Key": key} for key in keys]})
            if response.get("Errors"):
                raise RuntimeError("Không xoá được đầy đủ dữ liệu.")
        else:
            for key in keys:
                (self.root / key).unlink(missing_ok=True)

    def save(self, item, original_bytes, original_type, preview_bytes, visualization_bytes):
        now = datetime.now(timezone.utc)
        record_id = now.strftime("%Y%m%dT%H%M%S%fZ") + "-" + uuid4().hex
        record = {key: value for key, value in item.items()
                  if key not in ("original_image_url", "visualization_image_url")}
        record.update(id=record_id, created_at=now.isoformat(), original_type=original_type)
        assets = [("original", original_bytes, original_type)]
        if preview_bytes:
            assets.append(("preview.jpg", preview_bytes, "image/jpeg"))
        if visualization_bytes:
            assets.append(("visualization.jpg", visualization_bytes, "image/jpeg"))
        record["has_visualization"] = bool(visualization_bytes)
        attempted = []
        try:
            for name, data, content_type in assets:
                key = self.key(record_id, name)
                attempted.append(key)
                self.put(key, data, content_type)
            # Publish metadata last: incomplete uploads never appear in history.
            key = self.key(record_id)
            attempted.append(key)
            self.put(key, json.dumps(record, ensure_ascii=False).encode("utf-8"), "application/json")
        except Exception:
            try:
                self.remove_keys(attempted)
            except Exception:
                pass
            raise
        return record

    def ids(self):
        if self.client:
            keys = (entry["Key"] for page in self.client.get_paginator("list_objects_v2").paginate(
                Bucket=self.bucket, Prefix=self.PREFIX) for entry in page.get("Contents", []))
        else:
            keys = (p.relative_to(self.root).as_posix()
                    for p in (self.root / self.PREFIX).glob("*/record.json"))
        return sorted((key.split("/")[-2] for key in keys if key.endswith("/record.json")), reverse=True)

    def get(self, record_id):
        return json.loads(self.read(self.key(record_id)))

    def delete(self, record_id):
        record = self.get(record_id)
        names = ["original", "preview.jpg"]
        if record["has_visualization"]:
            names.append("visualization.jpg")
        self.remove_keys([self.key(record_id, name) for name in names])
        # Keep the record available for retry if removing any image fails.
        self.remove_keys([self.key(record_id)])

    def signed_url(self, record_id, name):
        return self.client.generate_presigned_url(
            "get_object", Params={"Bucket": self.bucket, "Key": self.key(record_id, name)},
            ExpiresIn=900)

    def delete_all(self):
        # Snapshot IDs so uploads arriving during deletion are preserved.
        record_ids = self.ids()
        assets = [self.key(record_id, name) for record_id in record_ids
                  for name in ("original", "preview.jpg", "visualization.jpg")]
        for start in range(0, len(assets), 1000):
            self.remove_keys(assets[start:start + 1000])
        records = [self.key(record_id) for record_id in record_ids]
        for start in range(0, len(records), 1000):
            self.remove_keys(records[start:start + 1000])
