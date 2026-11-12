"""Where links live: DynamoDB in AWS, a dict for local runs."""

from __future__ import annotations

import threading
from collections.abc import Mapping
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Protocol

import boto3
from botocore.exceptions import ClientError

if TYPE_CHECKING:
    from mypy_boto3_dynamodb.service_resource import Table


@dataclass(frozen=True)
class Link:
    code: str
    url: str
    created_at: str
    hits: int = 0


class LinkStore(Protocol):
    def add(self, code: str, url: str) -> Link | None:
        """Store a new link; None if the code is already taken."""

    def get(self, code: str) -> Link | None: ...

    def hit(self, code: str) -> Link | None:
        """Count one visit and return the link; None if it does not exist."""

    def delete(self, code: str) -> bool:
        """Remove a link; False if it did not exist."""


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


class MemoryStore:
    def __init__(self) -> None:
        self._links: dict[str, Link] = {}
        self._lock = threading.Lock()

    def add(self, code: str, url: str) -> Link | None:
        with self._lock:
            if code in self._links:
                return None
            link = Link(code=code, url=url, created_at=_now())
            self._links[code] = link
            return link

    def get(self, code: str) -> Link | None:
        return self._links.get(code)

    def delete(self, code: str) -> bool:
        with self._lock:
            return self._links.pop(code, None) is not None

    def hit(self, code: str) -> Link | None:
        with self._lock:
            link = self._links.get(code)
            if link is None:
                return None
            link = replace(link, hits=link.hits + 1)
            self._links[code] = link
            return link


class DynamoStore:
    def __init__(self, table_name: str) -> None:
        self._table: Table = boto3.resource("dynamodb").Table(table_name)

    def add(self, code: str, url: str) -> Link | None:
        link = Link(code=code, url=url, created_at=_now())
        try:
            self._table.put_item(
                Item={"code": code, "url": url, "created_at": link.created_at, "hits": 0},
                ConditionExpression="attribute_not_exists(code)",
            )
        except ClientError as err:
            if err.response["Error"]["Code"] == "ConditionalCheckFailedException":
                return None
            raise
        return link

    def get(self, code: str) -> Link | None:
        item = self._table.get_item(Key={"code": code}).get("Item")
        return None if item is None else _from_item(item)

    def delete(self, code: str) -> bool:
        try:
            self._table.delete_item(
                Key={"code": code}, ConditionExpression="attribute_exists(code)"
            )
        except ClientError as err:
            if err.response["Error"]["Code"] == "ConditionalCheckFailedException":
                return False
            raise
        return True

    def hit(self, code: str) -> Link | None:
        try:
            result = self._table.update_item(
                Key={"code": code},
                UpdateExpression="ADD hits :one",
                ConditionExpression="attribute_exists(code)",
                ExpressionAttributeValues={":one": 1},
                ReturnValues="ALL_NEW",
            )
        except ClientError as err:
            if err.response["Error"]["Code"] == "ConditionalCheckFailedException":
                return None
            raise
        return _from_item(result["Attributes"])


def _from_item(item: Mapping[str, object]) -> Link:
    return Link(
        code=str(item["code"]),
        url=str(item["url"]),
        created_at=str(item["created_at"]),
        hits=int(str(item.get("hits", 0))),
    )
