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
            """
        )


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
