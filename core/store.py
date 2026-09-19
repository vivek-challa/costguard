from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timezone
from typing import Any

DB_PATH = os.getenv("COSTGUARD_DB", os.path.join(os.path.dirname(os.path.dirname(__file__)), "costguard.db"))


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    """Create the lightweight SQLite state store used by the MVP."""
    with _connect() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS observations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                service_name TEXT NOT NULL,
                observed_at TEXT NOT NULL,
                data_json TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_observations_service_time
            ON observations(service_name, observed_at);

            CREATE TABLE IF NOT EXISTS actions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                service_name TEXT NOT NULL,
                created_at TEXT NOT NULL,
                decision_json TEXT NOT NULL,
                result_json TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_actions_service_time
            ON actions(service_name, created_at);

            CREATE TABLE IF NOT EXISTS mock_cloud_state (
                service_name TEXT PRIMARY KEY,
                current_state_json TEXT NOT NULL,
                seed_state_json TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            """
        )
        row = conn.execute("SELECT count(*) FROM mock_cloud_state").fetchone()
        if not row or row[0] == 0:
            for sname in KNOWN_SEEDS.keys():
                reset_cloud_state(sname)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def add_observation(service_name: str, observation: dict[str, Any]) -> None:
    init_db()
    observed_at = str(observation.get("timestamp") or _now())
    with _connect() as conn:
        conn.execute(
            "INSERT INTO observations(service_name, observed_at, data_json) VALUES (?, ?, ?)",
            (service_name, observed_at, json.dumps(observation, default=str)),
        )
        # Keep a short rolling history for the hackathon MVP.
        conn.execute(
            """
            DELETE FROM observations
            WHERE service_name = ?
              AND id NOT IN (
                  SELECT id FROM observations
                  WHERE service_name = ?
                  ORDER BY id DESC LIMIT 30
              )
            """,
            (service_name, service_name),
        )


def get_history(service_name: str, limit: int = 10) -> list[dict[str, Any]]:
    init_db()
    limit = max(1, int(limit))
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT data_json
            FROM observations
            WHERE service_name = ?
            ORDER BY id DESC
            LIMIT ?
            """,
            (service_name, limit),
        ).fetchall()
    # Return chronological order so trend reasoning sees oldest -> newest.
    return [json.loads(row[0]) for row in reversed(rows)]


def add_action(service_name: str, decision: dict[str, Any], result: dict[str, Any]) -> None:
    init_db()
    with _connect() as conn:
        conn.execute(
            "INSERT INTO actions(service_name, created_at, decision_json, result_json) VALUES (?, ?, ?, ?)",
            (
                service_name,
                _now(),
                json.dumps(decision, default=str),
                json.dumps(result, default=str),
            ),
        )


def get_actions(service_name: str, limit: int = 20) -> list[dict[str, Any]]:
    init_db()
    limit = max(1, int(limit))
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT created_at, decision_json, result_json
            FROM actions
            WHERE service_name = ?
            ORDER BY id DESC
            LIMIT ?
            """,
            (service_name, limit),
        ).fetchall()
    return [
        {
            "created_at": row[0],
            "decision": json.loads(row[1]),
            "result": json.loads(row[2]),
        }
        for row in reversed(rows)
    ]


def get_all_actions(limit: int = 50) -> list[dict[str, Any]]:
    init_db()
    limit = max(1, int(limit))
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT service_name, created_at, decision_json, result_json
            FROM actions
            ORDER BY id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return [
        {
            "service_name": row[0],
            "created_at": row[1],
            "decision": json.loads(row[2]),
            "result": json.loads(row[3]),
        }
        for row in rows
    ]


KNOWN_SEEDS: dict[str, dict[str, Any]] = {
    "orders-api": {
        "service": "orders-api",
        "name": "orders-api",
        "instances": 4,
        "min_instances": 2,
        "max_instances": 8,
        "cpu_percent": 78.0,
        "requests_per_minute": 4200,
        "latency_ms": 260.0,
        "max_latency_ms": 300.0,
        "healthy": True,
        "cost_per_instance_hour": 27.75,
        "estimated_hourly_cost": 111.00,
        "timestamp": None,
    },
    "reports-worker": {
        "service": "reports-worker",
        "name": "reports-worker",
        "instances": 4,
        "min_instances": 1,
        "max_instances": 8,
        "cpu_percent": 9.0,
        "requests_per_minute": 0,
        "latency_ms": 80.0,
        "max_latency_ms": 300.0,
        "healthy": True,
        "cost_per_instance_hour": 18.50,
        "estimated_hourly_cost": 74.00,
        "timestamp": None,
    },
    "checkout-api": {
        "service": "checkout-api",
        "name": "checkout-api",
        "instances": 4,
        "min_instances": 2,
        "max_instances": 8,
        "cpu_percent": 24.0,
        "requests_per_minute": 900,
        "latency_ms": 170.0,
        "max_latency_ms": 250.0,
        "healthy": True,
        "cost_per_instance_hour": 20.00,
        "estimated_hourly_cost": 80.00,
        "timestamp": None,
    },
    "payment-api": {
        "service": "payment-api",
        "name": "payment-api",
        "instances": 3,
        "min_instances": 2,
        "max_instances": 8,
        "cpu_percent": 91.0,
        "requests_per_minute": 6400,
        "latency_ms": 410.0,
        "max_latency_ms": 300.0,
        "healthy": True,
        "cost_per_instance_hour": 22.00,
        "estimated_hourly_cost": 66.00,
        "failure_sequence": ["capacity_unavailable"],
        "timestamp": None,
    },
}

DEFAULT_SEED_STATE = KNOWN_SEEDS["orders-api"]


def get_cloud_state(service_name: str = "orders-api") -> dict[str, Any]:
    """Fetch the active mock cloud state from SQLite, seeding if not initialized."""
    init_db()
    with _connect() as conn:
        row = conn.execute(
            "SELECT current_state_json FROM mock_cloud_state WHERE service_name = ?",
            (service_name,),
        ).fetchone()
        if row:
            return json.loads(row[0])

    # Not initialized yet, seed default state
    return reset_cloud_state(service_name)


def save_cloud_state(service_name: str, state: dict[str, Any]) -> None:
    """Persist the active mock cloud state in SQLite."""
    init_db()
    now_ts = _now()
    state_to_save = dict(state)
    state_to_save["timestamp"] = now_ts
    state_to_save.setdefault("name", service_name)
    state_to_save.setdefault("service", service_name)
    seed = get_seed_state(service_name)

    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO mock_cloud_state (service_name, current_state_json, seed_state_json, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(service_name) DO UPDATE SET
                current_state_json = excluded.current_state_json,
                updated_at = excluded.updated_at
            """,
            (
                service_name,
                json.dumps(state_to_save, default=str),
                json.dumps(seed, default=str),
                now_ts,
            ),
        )


def get_seed_state(service_name: str = "orders-api") -> dict[str, Any]:
    """Fetch the initial seed state configured for this service."""
    init_db()
    with _connect() as conn:
        row = conn.execute(
            "SELECT seed_state_json FROM mock_cloud_state WHERE service_name = ?",
            (service_name,),
        ).fetchone()
        if row:
            return json.loads(row[0])

    if service_name in KNOWN_SEEDS:
        return dict(KNOWN_SEEDS[service_name])

    seed = dict(DEFAULT_SEED_STATE)
    seed["name"] = service_name
    seed["service"] = service_name
    return seed


def save_seed_state(service_name: str, seed: dict[str, Any]) -> None:
    """Update the initial seed state configured for this service."""
    init_db()
    now_ts = _now()
    seed_to_save = dict(seed)
    seed_to_save.setdefault("name", service_name)
    seed_to_save.setdefault("service", service_name)

    with _connect() as conn:
        row = conn.execute(
            "SELECT current_state_json FROM mock_cloud_state WHERE service_name = ?",
            (service_name,),
        ).fetchone()
        current_json = row[0] if row else json.dumps(seed_to_save, default=str)

        conn.execute(
            """
            INSERT INTO mock_cloud_state (service_name, current_state_json, seed_state_json, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(service_name) DO UPDATE SET
                seed_state_json = excluded.seed_state_json,
                updated_at = excluded.updated_at
            """,
            (service_name, current_json, json.dumps(seed_to_save, default=str), now_ts),
        )


def reset_cloud_state(service_name: str = "orders-api", seed: dict[str, Any] | None = None) -> dict[str, Any]:
    """Reset mock cloud state back to seed state in SQLite."""
    init_db()
    now_ts = _now()
    if seed is None:
        if service_name in KNOWN_SEEDS:
            seed = dict(KNOWN_SEEDS[service_name])
        else:
            seed = get_seed_state(service_name)
    else:
        seed = dict(seed)

    state = dict(seed)
    state["timestamp"] = now_ts
    state.setdefault("name", service_name)
    state.setdefault("service", service_name)
    state.setdefault("estimated_hourly_cost", round(float(state.get("instances", 1)) * float(state.get("cost_per_instance_hour", 10.0)), 2))

    with _connect() as conn:
        conn.execute("DELETE FROM observations WHERE service_name = ?", (service_name,))
        conn.execute(
            """
            INSERT INTO mock_cloud_state (service_name, current_state_json, seed_state_json, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(service_name) DO UPDATE SET
                current_state_json = excluded.current_state_json,
                seed_state_json = excluded.seed_state_json,
                updated_at = excluded.updated_at
            """,
            (
                service_name,
                json.dumps(state, default=str),
                json.dumps(seed, default=str),
                now_ts,
            ),
        )
    # Seed short baseline observations so history checks pass for idle evaluation
    rpm_seed = float(state.get("requests_per_minute", 0))
    for _ in range(3):
        add_observation(service_name, state)
    return state


def clear_db(service_name: str = "orders-api", reset_env: bool = True) -> None:
    init_db()
    with _connect() as conn:
        conn.execute("DELETE FROM observations")
        conn.execute("DELETE FROM actions")
        conn.commit()
    if reset_env:
        for sname in KNOWN_SEEDS.keys():
            reset_cloud_state(sname)

