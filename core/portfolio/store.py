"""
Compass Phase A — per-user portfolio store (spec §4.1).

Layout (volume-persisted, per-user from day one):
    data/portfolio/<user_id>/portfolio.json
    data/portfolio/<user_id>/advice_ledger.jsonl      (append-only)
    data/portfolio/<user_id>/digests/<YYYY-MM-DD>.json

Atomic JSON writes (temp + rename), same pattern as PredictionStore.
"""
from __future__ import annotations

import csv
import io
import json
import logging
import re
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from filelock import FileLock

from core.config import settings
from backend.shared.schemas.portfolio import (
    AdviceRecord,
    Holding,
    Portfolio,
    TransactionRecord,
    WatchlistItem,
)

logger = logging.getLogger(__name__)

_USER_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


class PortfolioStore:
    def __init__(self, user_id: str | None = None, base_dir: str | None = None) -> None:
        self.user_id = (user_id or settings.PORTFOLIO_DEFAULT_USER_ID).strip()
        if not _USER_ID_RE.fullmatch(self.user_id):
            raise ValueError(f"invalid user_id {self.user_id!r} — allowed: [A-Za-z0-9_-], max 64 chars")
        self._dir = Path(base_dir or settings.PORTFOLIO_DATA_DIR) / self.user_id
        self._dir.mkdir(parents=True, exist_ok=True)
        # Cross-process guard for every read-modify-write on this user's
        # portfolio (AUD-001): API workers and the pipeline all contend on
        # portfolio.json. Re-entrant for the same FileLock instance, so an
        # outer locked() block may call the locking helpers below.
        self._lock = FileLock(str(self._dir / "portfolio.lock"), timeout=30)

    @contextmanager
    def locked(self):
        """Per-user critical section for load→mutate→save sequences."""
        with self._lock:
            yield self

    # ------------------------------------------------------------------
    # Paths
    # ------------------------------------------------------------------
    def _portfolio_path(self) -> Path:
        return self._dir / "portfolio.json"

    def _ledger_path(self) -> Path:
        return self._dir / "advice_ledger.jsonl"

    def _transactions_path(self) -> Path:
        return self._dir / "transactions.jsonl"

    def _value_history_path(self) -> Path:
        return self._dir / "value_history.jsonl"

    def _digest_dir(self) -> Path:
        d = self._dir / "digests"
        d.mkdir(parents=True, exist_ok=True)
        return d

    # ------------------------------------------------------------------
    # Atomic write helper
    # ------------------------------------------------------------------
    def _write_json(self, path: Path, data: dict) -> None:
        """Write JSON atomically via a temp file to avoid partial writes."""
        tmp = path.with_suffix(".tmp")
        try:
            tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
            tmp.replace(path)
        except OSError as exc:
            logger.error("[PortfolioStore] Write failed for %s: %s", path.name, exc)
            try:
                tmp.unlink(missing_ok=True)
            except OSError:
                pass
            raise RuntimeError(f"Write failed for {path.name}: {exc}") from exc

    # ------------------------------------------------------------------
    # Portfolio CRUD
    # ------------------------------------------------------------------
    def load(self) -> Portfolio:
        path = self._portfolio_path()
        if not path.exists():
            return Portfolio(user_id=self.user_id)
        try:
            return Portfolio(**json.loads(path.read_text(encoding="utf-8")))
        except Exception as exc:
            logger.error("[PortfolioStore] failed to read %s: %s", path, exc)
            try:
                quarantine = path.with_name(
                    f"portfolio.json.corrupt-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')}"
                )
                path.rename(quarantine)
                logger.error("[PortfolioStore] quarantined corrupt file to %s", quarantine)
            except OSError:
                pass
            return Portfolio(user_id=self.user_id)

    def save(self, p: Portfolio) -> None:
        p.updated_at = datetime.now(timezone.utc).isoformat()
        self._write_json(self._portfolio_path(), p.model_dump())

    def add_holding(self, h: Holding) -> Portfolio:
        h.symbol = h.symbol.strip().upper()
        if h.qty <= 0 or h.avg_buy_price <= 0:
            raise ValueError(f"qty and avg_buy_price must be positive: {h.symbol}")
        with self._lock:
            p = self.load()
            existing = next((x for x in p.holdings if x.symbol == h.symbol), None)
            if existing:
                # Merge lots: weighted average on BOTH raw and adjusted figures.
                total_qty = existing.qty + h.qty
                existing.avg_buy_price = (
                    existing.avg_buy_price * existing.qty + h.avg_buy_price * h.qty
                ) / total_qty
                adj_total = existing.adj_qty + h.adj_qty
                if adj_total <= 0:
                    raise ValueError(f"adjusted quantity must be positive after merge: {h.symbol}")
                existing.adj_avg_price = (
                    existing.adj_avg_price * existing.adj_qty + h.adj_avg_price * h.adj_qty
                ) / adj_total
                existing.qty = total_qty
                existing.adj_qty = adj_total
            else:
                p.holdings.append(h)
            self.save(p)
            return p

    def remove_holding(self, symbol: str) -> bool:
        with self._lock:
            p = self.load()
            before = len(p.holdings)
            p.holdings = [h for h in p.holdings if h.symbol != symbol.upper()]
            if len(p.holdings) == before:
                return False
            self.save(p)
            return True

    def add_watchlist(self, w: WatchlistItem) -> Portfolio:
        w.symbol = w.symbol.strip().upper()
        with self._lock:
            p = self.load()
            if not any(x.symbol == w.symbol for x in p.watchlist):
                p.watchlist.append(w)
                self.save(p)
            return p

    def remove_watchlist(self, symbol: str) -> bool:
        with self._lock:
            p = self.load()
            before = len(p.watchlist)
            p.watchlist = [w for w in p.watchlist if w.symbol != symbol.upper()]
            if len(p.watchlist) == before:
                return False
            self.save(p)
            return True

    # ------------------------------------------------------------------
    # Advice ledger (append-only JSONL — spec §5.3)
    # ------------------------------------------------------------------
    def append_advice(self, rec: AdviceRecord) -> None:
        with open(self._ledger_path(), "a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec.model_dump(), ensure_ascii=False) + "\n")

    def load_advice(self, limit: int = 200) -> list[AdviceRecord]:
        path = self._ledger_path()
        if not path.exists():
            return []
        records: list[AdviceRecord] = []
        for line in path.read_text(encoding="utf-8").splitlines()[-limit:]:
            line = line.strip()
            if not line:
                continue
            try:
                records.append(AdviceRecord(**json.loads(line)))
            except Exception as exc:
                logger.warning("[PortfolioStore] skipping bad ledger line: %s", exc)
        return records

    # ------------------------------------------------------------------
    # Transactions ledger (append-only JSONL — Autopilot spec §3.2)
    # ------------------------------------------------------------------
    def append_transaction(self, rec: TransactionRecord) -> None:
        with open(self._transactions_path(), "a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec.model_dump(), ensure_ascii=False) + "\n")

    def load_transactions(self, limit: int = 200) -> list[TransactionRecord]:
        path = self._transactions_path()
        if not path.exists():
            return []
        records: list[TransactionRecord] = []
        for line in path.read_text(encoding="utf-8").splitlines()[-limit:]:
            line = line.strip()
            if not line:
                continue
            try:
                records.append(TransactionRecord(**json.loads(line)))
            except Exception as exc:
                logger.warning("[PortfolioStore] skipping bad txn line: %s", exc)
        return records

    # ------------------------------------------------------------------
    # Daily value history (append-only JSONL — Autopilot spec §3.3)
    # ------------------------------------------------------------------
    def append_value_point(self, point: dict) -> None:
        with open(self._value_history_path(), "a", encoding="utf-8") as fh:
            fh.write(json.dumps(point, ensure_ascii=False) + "\n")

    def load_value_history(self, limit: int = 400) -> list[dict]:
        path = self._value_history_path()
        if not path.exists():
            return []
        points: list[dict] = []
        for line in path.read_text(encoding="utf-8").splitlines()[-limit:]:
            line = line.strip()
            if not line:
                continue
            try:
                points.append(json.loads(line))
            except Exception as exc:
                logger.warning("[PortfolioStore] skipping bad value line: %s", exc)
        return points

    def reduce_holding(self, symbol: str, sell_qty: float, price: float) -> tuple[float, bool]:
        """Sell sell_qty shares of symbol at price. Returns (realized_pnl,
        removed). Raises ValueError for unknown symbol or overdraw."""
        with self._lock:
            p = self.load()
            h = next((x for x in p.holdings if x.symbol == symbol.upper()), None)
            if h is None:
                raise ValueError(f"no holding {symbol.upper()}")
            realized = h.sell(sell_qty, price)
            removed = h.adj_qty <= 1e-9
            if removed:
                p.holdings = [x for x in p.holdings if x.symbol != h.symbol]
            self.save(p)
            return realized, removed

    # ------------------------------------------------------------------
    # Digests
    # ------------------------------------------------------------------
    def save_digest(self, digest: dict) -> Path:
        path = self._digest_dir() / f"{digest['date']}.json"
        self._write_json(path, digest)
        return path

    def load_latest_digest(self) -> dict | None:
        digest_dir = self._dir / "digests"
        if not digest_dir.exists():
            return None
        files = sorted(digest_dir.glob("*.json"))
        if not files:
            return None
        try:
            return json.loads(files[-1].read_text(encoding="utf-8"))
        except Exception as exc:
            logger.error("[PortfolioStore] failed to read digest %s: %s", files[-1], exc)
            return None

    # ------------------------------------------------------------------
    # Briefs + weekly reviews (Compass Phase C, M4)
    # ------------------------------------------------------------------
    def _dated_dir(self, name: str) -> Path:
        d = self._dir / name
        d.mkdir(parents=True, exist_ok=True)
        return d

    def _load_latest_dated(self, name: str) -> dict | None:
        d = self._dir / name
        if not d.exists():
            return None
        files = sorted(d.glob("*.json"))
        if not files:
            return None
        try:
            return json.loads(files[-1].read_text(encoding="utf-8"))
        except Exception as exc:
            logger.error("[PortfolioStore] failed to read %s: %s", files[-1], exc)
            return None

    def save_brief(self, brief: dict) -> Path:
        path = self._dated_dir("briefs") / f"{brief['date']}.json"
        self._write_json(path, brief)
        return path

    def load_latest_brief(self) -> dict | None:
        return self._load_latest_dated("briefs")

    def save_weekly(self, review: dict) -> Path:
        path = self._dated_dir("weekly") / f"{review['date']}.json"
        self._write_json(path, review)
        return path

    def load_latest_weekly(self) -> dict | None:
        return self._load_latest_dated("weekly")


# ---------------------------------------------------------------------------
# CSV import (spec §4.2): symbol,sector,qty,avg_buy_price,buy_date
# avg_buy_price may be blank -> price_lookup(symbol, buy_date) fills it
# (real NSE close on the entry date — virtual-first pricing).
# ---------------------------------------------------------------------------

def import_csv(
    text: str,
    user_id: str | None = None,
    base_dir: str | None = None,
    price_lookup=None,
) -> dict:
    store = PortfolioStore(user_id=user_id, base_dir=base_dir)
    imported, errors = 0, []
    reader = csv.DictReader(io.StringIO(text))
    for i, row in enumerate(reader, start=2):   # row 1 = header
        try:
            symbol = (row["symbol"] or "").strip().upper()
            sector = (row["sector"] or "").strip()
            qty = float(row["qty"])
            buy_date = (row["buy_date"] or "").strip()
            raw_price = (row.get("avg_buy_price") or "").strip()
            if raw_price:
                price = float(raw_price)
            elif price_lookup is not None:
                price = float(price_lookup(symbol, buy_date))
            else:
                raise ValueError("avg_buy_price blank and no price_lookup available")
            store.add_holding(Holding(
                symbol=symbol, sector=sector, qty=qty, avg_buy_price=price,
                adj_avg_price=price, adj_qty=qty, buy_date=buy_date,
            ))
            imported += 1
        except Exception as exc:
            errors.append({"row": i, "error": str(exc)})
    return {"imported": imported, "errors": errors}


def list_user_ids(base_dir: str | None = None) -> list[str]:
    root = Path(base_dir or settings.PORTFOLIO_DATA_DIR)
    if not root.exists():
        return []
    return [d.name for d in root.iterdir() if d.is_dir() and (d / "portfolio.json").exists()]
