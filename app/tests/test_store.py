import pytest

from shortlinks.codes import ALPHABET, CODE_LENGTH, is_valid_code, new_code
from shortlinks.config import load_settings
from shortlinks.store import DynamoStore, MemoryStore


def test_codes_are_valid_and_differ() -> None:
    codes = {new_code() for _ in range(500)}
    assert len(codes) == 500
    assert all(len(c) == CODE_LENGTH and set(c) <= set(ALPHABET) for c in codes)
    assert all(is_valid_code(c) for c in codes)
    assert not is_valid_code("abc")
    assert not is_valid_code("abc-def")


def test_memory_store_add_get_hit() -> None:
    store = MemoryStore()
    assert store.add("Abc1234", "https://example.com") is not None
    assert store.add("Abc1234", "https://other.example.com") is None
    assert store.hit("Abc1234").hits == 1  # type: ignore[union-attr]
    assert store.get("Abc1234").hits == 1  # type: ignore[union-attr]
    assert store.get("Zzz9999") is None
    assert store.hit("Zzz9999") is None


def test_dynamo_store_add_get_hit(dynamo_store: DynamoStore) -> None:
    link = dynamo_store.add("Abc1234", "https://example.com")
    assert link is not None and link.hits == 0
    assert dynamo_store.add("Abc1234", "https://other.example.com") is None
    assert dynamo_store.hit("Abc1234").hits == 1  # type: ignore[union-attr]
    assert dynamo_store.hit("Abc1234").hits == 2  # type: ignore[union-attr]
    stored = dynamo_store.get("Abc1234")
    assert stored is not None and stored.url == "https://example.com" and stored.hits == 2


def test_dynamo_store_missing_code(dynamo_store: DynamoStore) -> None:
    assert dynamo_store.get("Zzz9999") is None
    assert dynamo_store.hit("Zzz9999") is None


def test_settings_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("APP_VERSION", "deadbee")
    monkeypatch.setenv("TABLE_NAME", "t")
    settings = load_settings()
    assert settings.is_production
    assert settings.app_version == "deadbee"
    assert settings.table_name == "t"
    monkeypatch.setenv("TABLE_NAME", "")
    assert load_settings().table_name is None
