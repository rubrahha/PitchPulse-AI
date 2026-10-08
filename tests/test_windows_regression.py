"""Regression: original v1.0 raised ZoneInfoNotFoundError on many Windows hosts.
The chat API must never depend on OS IANA time zone availability.
"""
from dataclasses import replace
from fastapi.testclient import TestClient
import importlib
import zoneinfo

main = importlib.import_module("sportpulse.main")


class Headlines:
    async def news(self, sport='all', query='', limit=20):
        return {"items": [{"title": "Cricket board announces schedule", "summary": "Cricket news today",
                           "url": "https://example.org/story", "source": "Mock RSS",
                           "published": "2026-10-08T07:00:00+00:00"}], "errors": []}


class OfflineHeadlines:
    async def news(self, sport='all', query='', limit=20):
        raise ConnectionError("Network is offline")


def test_chat_works_even_without_system_timezone_database(monkeypatch):
    def unavailable(*_args, **_kwargs):
        raise zoneinfo.ZoneInfoNotFoundError("No timezone database installed")

    monkeypatch.setattr(zoneinfo, "ZoneInfo", unavailable)
    monkeypatch.setattr(main, "settings", replace(main.Settings(), openai_api_key="", llm_provider="openai"))
    with TestClient(main.app) as client:
        monkeypatch.setattr(main.app.state.sources, "news", Headlines().news)
        r = client.post("/api/chat", json={"message": "Give me the latest cricket headlines"})
        assert r.status_code == 200, r.text
        j = r.json()
        assert j["mode"] == "news_reader"
        assert "Cricket board announces schedule" in j["answer"]
        assert j["sport"] == "cricket"
        assert j["sources"][0]["url"] == "https://example.org/story"
        assert j["data_as_of"].endswith("+00:00")


def test_chat_offline_returns_useful_200_instead_of_503(monkeypatch):
    monkeypatch.setattr(main, "settings", replace(main.Settings(), openai_api_key="", llm_provider="openai"))
    with TestClient(main.app) as client:
        monkeypatch.setattr(main.app.state.sources, "news", OfflineHeadlines().news)
        r = client.post("/api/chat", json={"message": "Give me the latest cricket headlines"})
        assert r.status_code == 200, r.text
        assert "couldn't verify" in r.json()["answer"]


def test_health_reports_current_version():
    with TestClient(main.app) as client:
        assert client.get("/api/health").json()["version"] == "1.3.0"
