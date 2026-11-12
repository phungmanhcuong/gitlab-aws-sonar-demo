from collections.abc import Iterator

import boto3
import pytest
from fastapi.testclient import TestClient
from moto import mock_aws

from shortlinks.config import Settings
from shortlinks.main import create_app
from shortlinks.store import DynamoStore, MemoryStore

TABLE = "shortlinks-test-links"


@pytest.fixture
def settings() -> Settings:
    return Settings(app_env="test", app_version="abc1234", table_name=None)


@pytest.fixture
def client(settings: Settings) -> TestClient:
    return TestClient(create_app(settings, MemoryStore()), follow_redirects=False)


@pytest.fixture
def dynamo_store(monkeypatch: pytest.MonkeyPatch) -> Iterator[DynamoStore]:
    monkeypatch.setenv("AWS_DEFAULT_REGION", "ap-southeast-1")
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
    with mock_aws():
        boto3.client("dynamodb").create_table(
            TableName=TABLE,
            KeySchema=[{"AttributeName": "code", "KeyType": "HASH"}],
            AttributeDefinitions=[{"AttributeName": "code", "AttributeType": "S"}],
            BillingMode="PAY_PER_REQUEST",
        )
        yield DynamoStore(TABLE)
