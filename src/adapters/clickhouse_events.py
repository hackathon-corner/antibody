"""ClickHouse evidence store for `Event` records (owner: C).

ClickHouse holds the event history used by the evidence API and report. It is
not the authoritative release store (PRD section 6): host state transitions
live in the host's transactional store, and events only explain them.

Rows are deduplicated by `event_id`: the table is a ReplacingMergeTree and
every read uses `LIMIT 1 BY event_id`, because merges happen lazily.
Credentials come from the environment (or an ignored `.env`), never from code.
"""

from __future__ import annotations

import hashlib
import os
from dataclasses import fields
from datetime import datetime, timezone
from pathlib import Path

from contracts import Event

TABLE = "events"

DDL = f"""
CREATE TABLE IF NOT EXISTS {TABLE} (
    event_id       String,
    run_id         String,
    candidate_hash Nullable(String),
    release_ref    Nullable(String),
    event_type     LowCardinality(String),
    emitter        LowCardinality(String),
    observed_at    DateTime64(3, 'UTC'),
    outcome        LowCardinality(String),
    artifact_ref   Nullable(String),
    detail         Nullable(String),
    inserted_at    DateTime64(3, 'UTC') DEFAULT now64(3)
)
ENGINE = ReplacingMergeTree(inserted_at)
ORDER BY (run_id, observed_at, event_id)
"""

# Columns added after the first deploy of the table; ensure_schema() adds them to existing tables.
MIGRATIONS = ("ALTER TABLE {table} ADD COLUMN IF NOT EXISTS detail Nullable(String) AFTER artifact_ref",)

COLUMNS = tuple(f.name for f in fields(Event))
ENV_KEYS = ("CLICKHOUSE_HOST", "CLICKHOUSE_PORT", "CLICKHOUSE_USER", "CLICKHOUSE_PASSWORD", "CLICKHOUSE_DATABASE")


class ClickHouseConfigError(RuntimeError):
    """Raised when connection settings are missing; never falls back to a fake store."""


def stable_event_id(run_id: str, event_type: str, emitter: str, key: str) -> str:
    """Deterministic ID so a retried insert of the same observation deduplicates."""
    digest = hashlib.sha256("\x1f".join((run_id, event_type, emitter, key)).encode()).hexdigest()
    return f"evt_{digest[:32]}"


def load_settings(env_file: str | Path | None = None) -> dict[str, str]:
    """Process environment first, then KEY=VALUE lines from an ignored .env file."""
    settings: dict[str, str] = {}
    path = Path(env_file) if env_file else Path(__file__).resolve().parents[2] / ".env"
    if path.is_file():
        for line in path.read_text().splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                key, value = line.split("=", 1)
                settings[key.strip()] = value.strip()
    settings.update({k: os.environ[k] for k in ENV_KEYS if os.environ.get(k)})
    missing = [k for k in ENV_KEYS if not settings.get(k)]
    if missing:
        raise ClickHouseConfigError(f"missing ClickHouse settings: {', '.join(missing)}")
    if ":" in settings["CLICKHOUSE_HOST"] or "/" in settings["CLICKHOUSE_HOST"]:
        raise ClickHouseConfigError("CLICKHOUSE_HOST must be a bare hostname (no scheme or port)")
    return settings


def event_to_row(event: Event) -> list:
    if event.observed_at.tzinfo is None:
        raise ValueError("observed_at must be timezone-aware")
    return [getattr(event, c) for c in COLUMNS]


def row_to_event(row: dict) -> Event:
    observed_at = row["observed_at"]
    if observed_at.tzinfo is None:
        observed_at = observed_at.replace(tzinfo=timezone.utc)
    return Event(**{**{c: row[c] for c in COLUMNS}, "observed_at": observed_at})


class ClickHouseEventStore:
    def __init__(self, client) -> None:
        self._client = client

    @classmethod
    def from_env(cls, env_file: str | Path | None = None) -> "ClickHouseEventStore":
        import clickhouse_connect

        s = load_settings(env_file)
        client = clickhouse_connect.get_client(
            host=s["CLICKHOUSE_HOST"],
            port=int(s["CLICKHOUSE_PORT"]),
            username=s["CLICKHOUSE_USER"],
            password=s["CLICKHOUSE_PASSWORD"],
            database=s["CLICKHOUSE_DATABASE"],
            secure=True,
        )
        return cls(client)

    def ping(self) -> str:
        """Return the server version; raises if the service is unreachable."""
        return str(self._client.command("SELECT version()"))

    def ensure_schema(self) -> None:
        self._client.command(DDL)
        for statement in MIGRATIONS:
            self._client.command(statement.format(table=TABLE))

    def insert(self, events: list[Event]) -> int:
        if not events:
            return 0
        self._client.insert(TABLE, [event_to_row(e) for e in events], column_names=list(COLUMNS))
        return len(events)

    def emit(self, event: Event) -> None:
        """`agent.EventSink` implementation: write one event as it happens (Q9 in docs/collab.md)."""
        self.insert([event])

    def events_for_run(self, run_id: str) -> list[Event]:
        result = self._client.query(
            f"SELECT {', '.join(COLUMNS)} FROM {TABLE} WHERE run_id = %(run_id)s "
            "ORDER BY observed_at, event_id, inserted_at DESC LIMIT 1 BY event_id",
            parameters={"run_id": run_id},
        )
        return [row_to_event(r) for r in result.named_results()]

    def run_ids(self, limit: int = 50) -> list[tuple[str, datetime]]:
        result = self._client.query(
            f"SELECT run_id, max(observed_at) AS last_seen FROM {TABLE} "
            "GROUP BY run_id ORDER BY last_seen DESC LIMIT %(limit)s",
            parameters={"limit": limit},
        )
        return [(r[0], r[1] if r[1].tzinfo else r[1].replace(tzinfo=timezone.utc)) for r in result.result_rows]
