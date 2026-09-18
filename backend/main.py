from fastapi import FastAPI, HTTPException
from typing import Any
from datetime import datetime, timezone
import copy
import math

app = FastAPI(title="CostGuard Mock Cloud Control API", version="1.0")
STATES: dict[str, dict] = {}

def utc_now():
    return datetime.now(timezone.utc).isoformat()

def normalized(s):
    x = copy.deepcopy(s)
    x.setdefault("instances", 1)
    x.setdefault("min_instances", 1)
    x.setdefault("max_instances", 10)
    x.setdefault("latency_ms", 100)
    x.setdefault("max_latency_ms", 300)
    x.setdefault("cpu_percent", 20)
    x.setdefault("requests_per_minute", 0)
    x.setdefault("healthy", True)
    x.setdefault("cost_per_instance_hour", 10.0)
    x.setdefault("timestamp", utc_now())
    x["estimated_hourly_cost"] = round(x["instances"] * x["cost_per_instance_hour"], 2)
    return x

@app.get("/health")
def health():
    return {"status":"ok","service":"CostGuard Mock Cloud Control API"}

@app.post("/load_state")
def load_state(payload: dict[str, Any]):
    service = normalized(payload["service"])
    STATES[service["name"]] = service
    return {"status":"loaded","service":service}

@app.get("/state/{service_name}")
def get_state(service_name: str):
    if service_name not in STATES:
        raise HTTPException(404, "service not loaded")
    return STATES[service_name]

@app.post("/refresh")
def refresh(payload: dict[str, Any]):
    service = normalized(payload["service"])
    latest = payload.get("latest_traffic") or {}
    if latest.get("requests_per_minute") is not None:
        old = max(1, float(service.get("requests_per_minute",0)))
        new = float(latest["requests_per_minute"])
        service["requests_per_minute"] = new
        # Simulated fresh full pull: latency rises with load, but remains bounded.
        service["latency_ms"] = round(max(20, float(service.get("latency_ms",80)) * math.sqrt(max(1,new/old))), 1)
        service["cpu_percent"] = round(min(99, float(service.get("cpu_percent",20)) * min(2.0,max(1,new/old)**0.35)), 1)
    service["timestamp"] = latest.get("timestamp") or utc_now()
    service["estimated_hourly_cost"] = round(service["instances"] * service["cost_per_instance_hour"], 2)
    STATES[service["name"]] = service
    return {"status":"refreshed","service":service}

@app.post("/execute")
def execute(payload: dict[str, Any]):
    name = payload["service_name"]
    action = payload["action"]
    if name not in STATES:
        raise HTTPException(404, "service not loaded")
    before = copy.deepcopy(STATES[name])
    service = STATES[name]

    sequence = service.get("failure_sequence", [])
    if sequence:
        failure = sequence.pop(0)
        service["failure_sequence"] = sequence
        return {"status":"failed","error":failure,"message":f"Injected failure: {failure}",
                "before":before,"after":copy.deepcopy(service),
                "cost_before":before["estimated_hourly_cost"],"cost_after":service["estimated_hourly_cost"]}

    kind = action.get("action","no_action")
    target = action.get("target_instances")
    if kind in {"scale_up","scale_down","resize"}:
        target = int(target)
        target = max(int(service["min_instances"]), min(int(service["max_instances"]), target))
        old = max(1,int(service["instances"]))
        service["instances"] = target
        service["latency_ms"] = round(float(service["latency_ms"]) * math.sqrt(old/max(1,target)), 1)
        service["cpu_percent"] = round(float(service["cpu_percent"]) * old/max(1,target), 1)
    elif kind == "stop_service":
        service["instances"] = 0
        service["latency_ms"] = 0
        service["cpu_percent"] = 0
        service["requests_per_minute"] = 0
    elif kind == "delay_batch":
        # Simulate moving non-urgent batch work to a cheaper window.
        service["batch_cost_factor"] = 0.90
    elif kind == "no_action":
        pass
    else:
        return {"status":"failed","error":"unsupported_action","before":before,"after":before,
                "cost_before":before["estimated_hourly_cost"],"cost_after":before["estimated_hourly_cost"]}

    service["timestamp"] = utc_now()
    service["estimated_hourly_cost"] = round(service["instances"] * service["cost_per_instance_hour"] *
                                              float(service.get("batch_cost_factor",1.0)), 2)
    STATES[name] = service
    return {"status":"success","error":None,"message":f"{kind} executed",
            "before":before,"after":copy.deepcopy(service),
            "cost_before":before["estimated_hourly_cost"],"cost_after":service["estimated_hourly_cost"]}

@app.post("/reset")
def reset():
    STATES.clear()
    return {"status":"reset"}
