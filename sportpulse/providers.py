"""Trusted sources: BBC RSS, CricketData/CricAPI and football-data.org v4.

Only constant upstream hosts are contacted, preventing client-controlled SSRF.
"""
import asyncio
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from html import unescape
import re
import time
from urllib.parse import urlencode, urlparse
from typing import Any
from defusedxml import ElementTree as ET
import httpx

BBC_FEEDS = {
    "cricket": "https://feeds.bbci.co.uk/sport/cricket/rss.xml",
    "football": "https://feeds.bbci.co.uk/sport/football/rss.xml",
    "all": "https://feeds.bbci.co.uk/sport/rss.xml",
}
GOOGLE_NEWS_RSS = "https://news.google.com/rss/search"
CRICKET_URL = "https://api.cricapi.com/v1/currentMatches"
FOOTBALL_URL = "https://api.football-data.org/v4/matches"
MAX_FEED_BYTES = 1_500_000


def clean_text(value: str | None) -> str:
    """Remove feed HTML and normalize whitespace."""
    return re.sub(r"\s+", " ", unescape(re.sub(r"<[^>]*>", " ", value or ""))).strip()


def safe_link(value: str | None) -> str:
    url = (value or "").strip()
    parts = urlparse(url)
    if parts.scheme not in ("https", "http") or not parts.hostname or parts.username or parts.password:
        return ""
    return url if len(url) <= 1800 else ""


def to_iso(value: str | None) -> str | None:
    if not value:
        return None
    try:
        return parsedate_to_datetime(value).astimezone(timezone.utc).isoformat()
    except (ValueError, TypeError, IndexError, OverflowError):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc).isoformat()
        except (ValueError, TypeError):
            return None


def parse_rss(blob: bytes, sport: str, provider: str) -> list[dict]:
    root = ET.fromstring(blob)
    result: list[dict] = []
    for item in root.findall(".//item")[:40]:
        get = lambda name: item.findtext(name, default="")
        title = clean_text(get("title"))[:240]
        link = safe_link(get("link"))
        if not title or not link:
            continue
        result.append({
            "title": title,
            "summary": clean_text(get("description"))[:420],
            "url": link,
            "published": to_iso(get("pubDate")),
            "source": provider,
            "sport": sport,
        })
    return result


class TTLCache:
    """Single worker cache with per-key in-flight deduplication and stale fallback."""
    def __init__(self):
        self.data: dict[str, tuple[float, dict]] = {}
        self.locks: dict[str, asyncio.Lock] = {}

    async def get(self, key: str, ttl: int, loader):
        now = time.monotonic()
        item = self.data.get(key)
        if item and now < item[0]:
            return {**item[1], "cached": True}
        lock = self.locks.setdefault(key, asyncio.Lock())
        async with lock:
            item = self.data.get(key)
            if item and time.monotonic() < item[0]:
                return {**item[1], "cached": True}
            try:
                result = await loader()
                result["updated_at"] = datetime.now(timezone.utc).isoformat()
                result["cached"] = False
                self.data[key] = (time.monotonic() + ttl, result)
                return result
            except Exception:
                # If provider goes down, do not pretend an old result is live.
                if item:
                    return {**item[1], "cached": True, "stale": True,
                            "warning": "Provider unavailable: showing previously fetched data."}
                raise


class SportsSources:
    def __init__(self, settings, client: httpx.AsyncClient):
        self.settings = settings
        self.client = client
        self.cache = TTLCache()

    async def fetch_xml(self, url: str, params: dict | None = None) -> bytes:
        # Constant endpoints only: no arbitrary URLs are accepted from users.
        async with self.client.stream("GET", url, params=params, follow_redirects=False) as r:
            r.raise_for_status()
            chunks, size = [], 0
            async for chunk in r.aiter_bytes():
                size += len(chunk)
                if size > MAX_FEED_BYTES:
                    raise ValueError("News feed too large")
                chunks.append(chunk)
        return b"".join(chunks)

    async def news(self, sport: str = "all", query: str = "", limit: int = 14) -> dict:
        sport = sport if sport in BBC_FEEDS else "all"
        query = clean_text(query)[:90]
        limit = max(1, min(30, limit))
        key = f"news:{sport}:{query.lower()}:{limit}"

        async def loader():
            requests = [("BBC Sport", self.fetch_xml(BBC_FEEDS[sport]))]
            if query:
                q = f"{query} {('sports' if sport == 'all' else sport)} when:7d"
            elif sport == "cricket":
                q = "cricket news when:7d"
            elif sport == "football":
                q = "football soccer news when:7d"
            else:
                q = "sports cricket football when:7d"
            requests.append(("Google News", self.fetch_xml(GOOGLE_NEWS_RSS, {
                "q": q, "hl": "en-IN", "gl": "IN", "ceid": "IN:en"
            })))
            replies = await asyncio.gather(*(job for _, job in requests), return_exceptions=True)
            stories, errors = [], []
            for (label, _), result in zip(requests, replies):
                if isinstance(result, Exception):
                    errors.append(f"{label} unavailable")
                    continue
                try:
                    stories += parse_rss(result, sport, label)
                except (ET.ParseError, ValueError):
                    errors.append(f"{label} invalid feed")
            # Deduplicate headline wording from separate syndication feeds.
            unique, seen = [], set()
            for story in stories:
                norm = re.sub(r"\W+", "", story["title"].lower())[:120]
                if norm not in seen:
                    seen.add(norm)
                    unique.append(story)
            # Preserve freshness where a valid date is available.
            unique.sort(key=lambda s: s["published"] or "", reverse=True)
            if not unique and errors:
                raise RuntimeError("; ".join(errors))
            return {"items": unique[:limit], "errors": errors, "sport": sport}

        return await self.cache.get(key, self.settings.news_cache_seconds, loader)

    async def cricket(self) -> dict:
        if not self.settings.cricket_api_key:
            return {"items": [], "configured": False, "message": "Add CRICKET_API_KEY to .env for real cricket scores."}

        async def loader():
            response = await self.client.get(CRICKET_URL, params={
                "apikey": self.settings.cricket_api_key, "offset": 0
            })
            response.raise_for_status()
            payload = response.json()
            if payload.get("status") == "failure" or payload.get("error"):
                raise RuntimeError("Cricket provider rejected the request or key")
            matches = []
            for match in payload.get("data", [])[:40]:
                scores = []
                for score in match.get("score") or []:
                    if not isinstance(score, dict):
                        continue
                    scores.append({
                        "inning": str(score.get("inning", "Innings"))[:85],
                        "r": score.get("r"), "w": score.get("w"), "o": score.get("o")
                    })
                matches.append({
                    "id": str(match.get("id", ""))[:90],
                    "name": str(match.get("name", "Unknown match"))[:180],
                    "status": str(match.get("status", "Not available"))[:180],
                    "date": str(match.get("date", ""))[:32],
                    "venue": str(match.get("venue", ""))[:120],
                    "format": str(match.get("matchType", ""))[:16].upper(),
                    "live": bool(match.get("matchStarted")) and not bool(match.get("matchEnded")),
                    "score": scores[:4],
                })
            matches.sort(key=lambda m: (not m["live"], m["date"]))
            return {"items": matches[:20], "configured": True, "source": "CricketData.org"}

        return await self.cache.get("cricket", self.settings.cricket_cache_seconds, loader)

    async def football(self) -> dict:
        if not self.settings.football_api_key:
            return {"items": [], "configured": False, "message": "Add FOOTBALL_API_KEY to .env for real football scores."}

        async def loader():
            response = await self.client.get(FOOTBALL_URL,
                                             headers={"X-Auth-Token": self.settings.football_api_key})
            response.raise_for_status()
            payload = response.json()
            items = []
            for match in payload.get("matches", [])[:70]:
                home, away = match.get("homeTeam") or {}, match.get("awayTeam") or {}
                score = (match.get("score") or {}).get("fullTime") or {}
                items.append({
                    "id": str(match.get("id", "")),
                    "name": f"{home.get('shortName') or home.get('name', 'Home')} vs {away.get('shortName') or away.get('name', 'Away')}",
                    "home": home.get("shortName") or home.get("name") or "Home",
                    "away": away.get("shortName") or away.get("name") or "Away",
                    "home_goals": score.get("home"), "away_goals": score.get("away"),
                    "status": match.get("status", "UNKNOWN"),
                    "competition": (match.get("competition") or {}).get("name") or "Football",
                    "utc_date": match.get("utcDate"),
                    "live": match.get("status") in {"LIVE", "IN_PLAY", "PAUSED"},
                })
            items.sort(key=lambda m: (not m["live"], m["utc_date"] or ""))
            return {"items": items[:25], "configured": True, "source": "football-data.org"}

        return await self.cache.get("football", self.settings.football_cache_seconds, loader)
