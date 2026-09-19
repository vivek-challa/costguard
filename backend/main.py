from fastapi import FastAPI, HTTPException, Query
from typing import Any, Optional
from datetime import datetime, timezone
import copy
import math
from core.store import (
    get_cloud_state,
    save_cloud_state,
    reset_cloud_state,
    get_seed_state,
    save_seed_state,
    add_observation,
    add_action,
    clear_db,
    KNOWN_SEEDS,
)

app = FastAPI(title="CostGuard Mock Cloud Control API", version="2.0")

def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()

def normalized(s: dict[str, Any]) -> dict[str, Any]:
    x = copy.deepcopy(s)
    name = x.get("name") or x.get("service") or x.get("service_name") or "orders-api"
    x["name"] = name
    x["service"] = name
    defaults = KNOWN_SEEDS.get(name, KNOWN_SEEDS["orders-api"])
    for k, v in defaults.items():
        x.setdefault(k, v)
    x["timestamp"] = utc_now()
    x["estimated_hourly_cost"] = round(float(x["instances"]) * float(x["cost_per_instance_hour"]), 2)
    return x

@app.get("/health")
def health():
    return {"status": "ok", "service": "CostGuard Mock Cloud Control API", "persistence": "sqlite"}

# -----------------------------------------------------------------------------
# DEDICATED MOCK CLOUD CONTROL ENDPOINTS (V2 PERSISTENCE ARCHITECTURE)
# -----------------------------------------------------------------------------

@app.get("/cloud/state")
def cloud_state(service: str = Query("orders-api")):
    """Fetch the active mock cloud state from SQLite."""
    state = get_cloud_state(service)
    return state

@app.get("/cloud/initial_state")
def cloud_initial_state(service: str = Query("orders-api")):
    """Fetch the seed initial state configured for this service."""
    return get_seed_state(service)

@app.post("/cloud/seed")
def update_seed_state(payload: dict[str, Any]):
    """Update and persist the initial seed state."""
    service_name = payload.get("service") or payload.get("service_name") or "orders-api"
    seed = payload.get("seed") or payload.get("state") or payload
    if "seed" in payload and isinstance(payload["seed"], dict):
        seed = payload["seed"]
    norm_seed = normalized(seed)
    save_seed_state(service_name, norm_seed)
    return {"status": "saved", "service": service_name, "seed": norm_seed}

@app.post("/cloud/reset")
def cloud_reset(payload: Optional[dict[str, Any]] = None):
    """Reset the mock cloud state in SQLite back to the seed state, clearing history."""
    payload = payload or {}
    service_name = payload.get("service") or payload.get("service_name") or "orders-api"
    if isinstance(service_name, dict):
        service_name = service_name.get("name") or service_name.get("service") or "orders-api"
    if service_name in {"all", "both"}:
        results = {}
        for sname in KNOWN_SEEDS.keys():
            results[sname] = reset_cloud_state(sname)
        return {"status": "reset", "service": "all", "state": results.get("orders-api", {})}
    seed = payload.get("seed")
    state = reset_cloud_state(service_name, seed)
    return {"status": "reset", "service": service_name, "state": state}

@app.post("/cloud/refresh")
def cloud_refresh(payload: Optional[dict[str, Any]] = None):
    """Refresh active cloud telemetry timestamp and optional traffic."""
    payload = payload or {}
    service_name = payload.get("service") or payload.get("service_name") or "orders-api"
    if isinstance(service_name, dict):
        service_name = service_name.get("name") or service_name.get("service") or "orders-api"
    state = get_cloud_state(service_name)
    latest = payload.get("latest_traffic") or {}
    if latest.get("requests_per_minute") is not None:
        old_rpm = max(1, float(state.get("requests_per_minute", 4200)))
        new_rpm = float(latest["requests_per_minute"])
        state["requests_per_minute"] = new_rpm
        state["latency_ms"] = round(max(20.0, float(state.get("latency_ms", 260.0)) * math.sqrt(max(0.1, new_rpm / old_rpm))), 1)
        state["cpu_percent"] = round(min(99.0, float(state.get("cpu_percent", 78.0)) * min(2.0, (new_rpm / old_rpm) ** 0.35)), 1)
    state["timestamp"] = latest.get("timestamp") or utc_now()
    save_cloud_state(service_name, state)
    add_observation(service_name, state)
    return {"status": "refreshed", "service": state}

@app.post("/cloud/action")
def cloud_action(payload: dict[str, Any]):
    """Execute an autonomous action against the Mock Cloud API and persist state in SQLite."""
    service_name = payload.get("service") or payload.get("service_name") or "orders-api"
    if isinstance(service_name, dict):
        service_name = service_name.get("name") or service_name.get("service") or "orders-api"
    action_data = payload.get("action")
    if isinstance(action_data, str):
        action_data = {"action": action_data}
    elif not isinstance(action_data, dict):
        action_data = payload

    # Fetch current cloud state from SQLite
    before = get_cloud_state(service_name)
    service = copy.deepcopy(before)

    # Injected failure check
    sequence = service.get("failure_sequence", [])
    if sequence:
        failure = sequence.pop(0)
        service["failure_sequence"] = sequence
        save_cloud_state(service_name, service)
        failed_res = {
            "status": "failed",
            "error": failure,
            "message": f"Injected failure: {failure}",
            "before": before,
            "after": copy.deepcopy(service),
            "cost_before": before.get("estimated_hourly_cost", 0.0),
            "cost_after": service.get("estimated_hourly_cost", 0.0),
        }
        add_action(service_name, action_data, failed_res)
        return failed_res

    kind = action_data.get("action", "no_action")
    target = action_data.get("target_instances")
    amount = action_data.get("amount")

    current_i = int(service.get("instances", 4))
    min_i = int(service.get("min_instances", 2))
    max_i = int(service.get("max_instances", 8))

    if kind in {"scale_up", "scale_down", "resize"}:
        if target is None:
            if amount is not None:
                target = current_i + int(amount) if kind == "scale_up" else current_i - int(amount)
            else:
                target = current_i + 2 if kind == "scale_up" else max(min_i, current_i - 2)
        else:
            target = int(target)

        target = max(min_i, min(max_i, target))
        old = max(1, current_i)
        service["instances"] = target
        # Accurate square-root load scaling model: latency changes inversely with sqrt of instance capacity
        service["latency_ms"] = round(float(service["latency_ms"]) * math.sqrt(old / max(1, target)), 1)
        service["cpu_percent"] = round(min(100.0, max(5.0, float(service["cpu_percent"]) * (old / max(1, target)))), 1)

    elif kind == "stop_service":
        service["instances"] = 0
        service["latency_ms"] = 0.0
        service["cpu_percent"] = 0.0
        service["requests_per_minute"] = 0
    elif kind == "delay_batch":
        service["batch_cost_factor"] = 0.90
    elif kind == "no_action":
        pass
    else:
        unsupported_res = {
            "status": "failed",
            "error": "unsupported_action",
            "before": before,
            "after": before,
            "cost_before": before.get("estimated_hourly_cost", 0.0),
            "cost_after": before.get("estimated_hourly_cost", 0.0),
        }
        return unsupported_res

    service["timestamp"] = utc_now()
    cpih = float(service.get("cost_per_instance_hour", 27.75))
    service["estimated_hourly_cost"] = round(
        service["instances"] * cpih * float(service.get("batch_cost_factor", 1.0)), 2
    )

    # Persist the new state in SQLite
    save_cloud_state(service_name, service)
    # Record new observation in SQLite
    add_observation(service_name, service)

    success_res = {
        "status": "success",
        "error": None,
        "message": f"{kind} executed successfully",
        "before": before,
        "after": copy.deepcopy(service),
        "cost_before": before.get("estimated_hourly_cost", 0.0),
        "cost_after": service.get("estimated_hourly_cost", 0.0),
    }
    # Record action in SQLite
    add_action(service_name, action_data, success_res)

    return success_res

# -----------------------------------------------------------------------------
# BACKWARDS COMPATIBILITY ROUTES FOR EXISTING SCRIPTS
# -----------------------------------------------------------------------------

@app.post("/load_state")
def load_state(payload: dict[str, Any]):
    service = normalized(payload.get("service") or payload)
    name = service["name"]
    save_cloud_state(name, service)
    add_observation(name, service)
    return {"status": "loaded", "service": service}

@app.get("/state/{service_name}")
def get_state_compat(service_name: str):
    return get_cloud_state(service_name)

@app.post("/refresh")
def refresh_compat(payload: dict[str, Any]):
    return cloud_refresh(payload)

@app.post("/execute")
def execute_compat(payload: dict[str, Any]):
    return cloud_action(payload)

@app.post("/reset")
def reset_compat():
    return cloud_reset({"service": "orders-api"})
