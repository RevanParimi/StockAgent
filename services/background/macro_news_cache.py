"""
services/background/macro_news_cache.py
========================================
Daily JSON cache for background-fetched India macro/market news.

File layout: data/macro_news/YYYY-MM-DD_macro_feed.json
One file per day, created/appended by MacroNewsFetcher.
Retained for MACRO_NEWS_RETAIN_DAYS (default 90) then deleted.

Each entry schema:
  {
    "id":             "e001",
    "fetched_at":     "2026-05-12T09:00:00Z",   # ISO UTC
    "source":         "serper_news" | "newsapi_headlines",
    "title":          str,
    "snippet":        str,
    "url":            str,
    "published_date": "2026-05-12",              # ISO (normalised from relative)
    "severity":       "HIGH" | "MEDIUM" | "LOW",
    "impact_tags":    ["gold", "rbi", ...],      # constrained vocabulary
    "summary":        str,                       # 1 sentence from ReviewAgent LLM
  }

Atomic writes: write to .tmp then os.replace() — safe against concurrent reads.
URL dedup: same URL within the same day is silently skipped.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

_DATA_DIR = Path("data/macro_news")


def _today_file(d: date | None = None) -> Path:
    target = d or date.today()
    return _DATA_DIR / f"{target.isoformat()}_macro_feed.json"


def _load_file(path: Path) -> dict:
    if not path.exists():
        return {"date": path.stem[:10], "last_refresh": "", "refresh_count": 0, "entries": []}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.warning("[MacroNewsCache] Could not read %s: %s — treating as empty", path, exc)
        return {"date": path.stem[:10], "last_refresh": "", "refresh_count": 0, "entries": []}


def _save_file(path: Path, data: dict) -> None:
    """Atomic write: write to .tmp then rename."""
    _DATA_DIR.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    try:
        tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, path)
    except Exception as exc:
        logger.error("[MacroNewsCache] Write failed for %s: %s", path, exc)
        if tmp.exists():
            tmp.unlink(missing_ok=True)


class MacroNewsCache:
    """
    Read/write interface for the daily macro news JSON file.
    Thread-safe for single-writer / many-reader pattern (APScheduler writes,
    FastAPI request handlers read).  os.replace() is atomic on POSIX and
    Windows (since Python 3.3 on NTFS).
    """

    def add_entries(self, entries: list[dict]) -> int:
        """
        Merge new entries into today's file.  Skips duplicates by URL.
        Returns the number of entries actually added.
        Also runs retention cleanup (deletes files older than MACRO_NEWS_RETAIN_DAYS).
        """
        if not entries:
            return 0

        path = _today_file()
        data = _load_file(path)
        seen_urls: set[str] = {e.get("url", "") for e in data["entries"]}

        added = 0
        for entry in entries:
            url = entry.get("url", "")
            if url and url in seen_urls:
                continue
            # Assign sequential ID
            entry["id"] = f"e{len(data['entries']) + added + 1:04d}"
            entry.setdefault("fetched_at", datetime.now(timezone.utc).isoformat())
            data["entries"].append(entry)
            seen_urls.add(url)
            added += 1

        data["last_refresh"] = datetime.now(timezone.utc).isoformat()
        data["refresh_count"] = data.get("refresh_count", 0) + 1

        _save_file(path, data)
        self._cleanup_old_files()
        return added

    def get_high_severity(self, hours_back: int = 24) -> list[dict]:
        """Return HIGH-severity entries from the last `hours_back` hours (today + yesterday)."""
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours_back)
        cutoff_date = cutoff.date()

        entries: list[dict] = []
        for d in [date.today(), date.today() - timedelta(days=1)]:
            if d < cutoff_date:
                continue
            data = _load_file(_today_file(d))
            for e in data.get("entries", []):
                if e.get("severity") == "HIGH":
                    entries.append(e)

        return entries

    def get_all_today(self) -> list[dict]:
        """Return all entries for today, sorted HIGH → MEDIUM → LOW."""
        data = _load_file(_today_file())
        _sev_order = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}
        return sorted(
            data.get("entries", []),
            key=lambda x: _sev_order.get(x.get("severity", "LOW"), 2),
        )

    def get_formatted_context(self, max_items: int = 3) -> str:
        """
        Compact text block for injection into the chat system prompt.
        Only HIGH-severity items from the last 24h.  Empty string if nothing.
        """
        items = self.get_high_severity(hours_back=24)[:max_items]
        if not items:
            return ""
        lines = ["TRENDING MACRO TODAY (HIGH severity — background feed):"]
        for e in items:
            tags = ", ".join(e.get("impact_tags", []))
            pub  = e.get("published_date", "today")
            title = e.get("title", "")
            lines.append(f"• [{pub}] {title} [tags: {tags}]")
        return "\n".join(lines)

    def get_for_reviewer(self, max_items: int = 5) -> str:
        """
        Formatted HIGH items for the reviewer node's criterion 4 check.
        Includes impact_tags and summary so the reviewer LLM can reason about overlap.
        """
        items = self.get_high_severity(hours_back=24)[:max_items]
        if not items:
            return ""
        lines = []
        for i, e in enumerate(items, 1):
            tags = ", ".join(e.get("impact_tags", []))
            lines.append(
                f"{i}. [{e.get('published_date', '')}] {e.get('title', '')} "
                f"— {e.get('summary', '')} [tags: {tags}]"
            )
        return "\n".join(lines)

    def _cleanup_old_files(self) -> None:
        """Delete daily files older than MACRO_NEWS_RETAIN_DAYS."""
        try:
            from backend.shared.config import settings as _s
            retain_days = getattr(_s, "MACRO_NEWS_RETAIN_DAYS", 90)
        except Exception:
            retain_days = 90

        cutoff = date.today() - timedelta(days=retain_days)
        for f in _DATA_DIR.glob("*_macro_feed.json"):
            try:
                file_date = date.fromisoformat(f.name[:10])
                if file_date < cutoff:
                    f.unlink()
                    logger.info("[MacroNewsCache] Deleted old feed: %s", f.name)
            except Exception:
                pass
