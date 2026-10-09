import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

import pytest

from adapters.clickhouse_events import (
    COLUMNS,
    ClickHouseConfigError,
    event_to_row,
    load_settings,
    row_to_event,
    stable_event_id,
)
from contracts import Event


def make_event(**overrides) -> Event:
    base = dict(
        event_id="evt_1",
        run_id="r1",
        candidate_hash=None,
        release_ref=None,
        event_type="target.build",
        emitter="test",
        observed_at=datetime(2026, 10, 9, 20, 2, 33, tzinfo=timezone.utc),
        outcome="success",
        artifact_ref=None,
    )
    return Event(**{**base, **overrides})


def test_stable_event_id_is_deterministic_and_input_sensitive():
    a = stable_event_id("r1", "target.build", "gha", "step-1")
    assert a == stable_event_id("r1", "target.build", "gha", "step-1")
    assert a != stable_event_id("r1", "target.build", "gha", "step-2")
    assert a.startswith("evt_") and len(a) == 36


def test_row_round_trip_preserves_event():
    event = make_event(candidate_hash="abc", artifact_ref="https://example.invalid/run/1", detail='{"checks": 5}')
    row = dict(zip(COLUMNS, event_to_row(event)))
    assert row_to_event(row) == event


def test_naive_timestamps_rejected_on_write_and_treated_as_utc_on_read():
    with pytest.raises(ValueError):
        event_to_row(make_event(observed_at=datetime(2026, 10, 9, 20, 0)))
    row = dict(zip(COLUMNS, event_to_row(make_event())))
    row["observed_at"] = row["observed_at"].replace(tzinfo=None)
    assert row_to_event(row).observed_at.tzinfo == timezone.utc


def test_settings_require_every_key_and_bare_host(tmp_path, monkeypatch):
    for key in ("CLICKHOUSE_HOST", "CLICKHOUSE_PORT", "CLICKHOUSE_USER", "CLICKHOUSE_PASSWORD", "CLICKHOUSE_DATABASE"):
        monkeypatch.delenv(key, raising=False)
    env = tmp_path / ".env"
    env.write_text("CLICKHOUSE_HOST=h.example.invalid\nCLICKHOUSE_PORT=8443\n")
    with pytest.raises(ClickHouseConfigError, match="CLICKHOUSE_USER"):
        load_settings(env)
    env.write_text(
        "CLICKHOUSE_HOST=h.example.invalid:8443\nCLICKHOUSE_PORT=8443\nCLICKHOUSE_USER=u\n"
        "CLICKHOUSE_PASSWORD=p\nCLICKHOUSE_DATABASE=d\n"
    )
    with pytest.raises(ClickHouseConfigError, match="bare hostname"):
        load_settings(env)


def test_every_event_field_has_a_table_column():
    from adapters.clickhouse_events import DDL

    for column in COLUMNS:
        assert f"\n    {column} " in DDL, column


def test_store_satisfies_agent_event_sink():
    from adapters.clickhouse_events import ClickHouseEventStore

    class FakeClient:
        def __init__(self):
            self.rows = []

        def insert(self, table, rows, column_names):
            self.rows.extend(rows)

    client = FakeClient()
    ClickHouseEventStore(client).emit(make_event())
    assert len(client.rows) == 1
