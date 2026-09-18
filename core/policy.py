from typing import Any

SUPPORTED_ACTIONS = {"scale_up", "scale_down", "resize", "stop_service", "delay_batch", "no_action"}

def _target(action: dict, service: dict) -> int | None:
    kind = action.get("action")
    if kind in {"scale_up", "scale_down", "resize"}:
        return int(action.get("target_instances", service.get("instances", 0)))
    if kind == "stop_service":
        return 0
    return None

def projected_latency(service: dict, target: int) -> float:
    current = max(1, int(service.get("instances", 1)))
    current_latency = float(service.get("latency_ms", 0))
    # Simple simulator projection: capacity change changes latency inversely.
    return current_latency * ((current / max(1, target)) ** 0.5)

def validate_actions(service: dict, freshness: dict, candidates: list[dict], history: list[dict]) -> dict:
    min_i = int(service.get("min_instances", 1))
    max_i = int(service.get("max_instances", 10))
    current = int(service.get("instances", 1))
    max_latency = float(service.get("max_latency_ms", 300))
    healthy = bool(service.get("healthy", True))
    rpm = float(service.get("requests_per_minute", 0))
    approved = []
    rejected = []

    for raw in candidates:
        action = dict(raw)
        kind = action.get("action")
        target = _target(action, service)

        if kind not in SUPPORTED_ACTIONS:
            rejected.append({"action": kind, "reason": "unsupported action"})
            continue

        if kind == "no_action":
            approved.append({**action, "target_instances": current, "safety_reason": "explicit safe no-action"})
            continue

        if not healthy and kind not in {"scale_up", "no_action"}:
            rejected.append({"action": kind, "reason": "health gate: cost-saving action blocked while service is unhealthy"})
            continue

        if target is not None and (target < min_i or target > max_i):
            rejected.append({"action": kind, "target_instances": target, "reason": f"capacity must stay within [{min_i}, {max_i}]"})
            continue

        reducing = target is not None and target < current
        if reducing and freshness.get("stale"):
            rejected.append({"action": kind, "target_instances": target, "reason": "staleness gate: capacity reduction blocked until data is refreshed"})
            continue

        if reducing:
            # If latency is already within 15% of ceiling, never reduce.
            if float(service.get("latency_ms", 0)) >= max_latency * 0.85:
                rejected.append({"action": kind, "target_instances": target, "reason": "latency headroom is too small for a capacity reduction"})
                continue
            p = projected_latency(service, target)
            if p > max_latency:
                rejected.append({"action": kind, "target_instances": target, "reason": f"projected latency {p:.0f}ms exceeds {max_latency:.0f}ms"})
                continue
            if kind == "stop_service" or target < min_i:
                rejected.append({"action": kind, "target_instances": target, "reason": "target violates minimum capacity"})
                continue

        if kind == "stop_service" and rpm > 0:
            rejected.append({"action": kind, "reason": "idle gate: service is still receiving requests"})
            continue

        if kind == "scale_down" and rpm > 1:
            # Scale-down is still possible, but only with evidence in history.
            recent_rpm = [float(x.get("requests_per_minute", 999999)) for x in history[-3:]]
            if not recent_rpm or any(v > 5 for v in recent_rpm):
                rejected.append({"action": kind, "target_instances": target, "reason": "idle/capacity reduction requires recent near-zero traffic evidence"})
                continue

        if kind == "resize" and target is not None and target < current and rpm > 5:
            # conservative resize rule
            rejected.append({"action": kind, "target_instances": target, "reason": "resize reduction requires near-idle traffic"})
            continue

        if kind == "scale_up" and float(service.get("latency_ms", 0)) >= max_latency * 0.85:
            action["priority"] = "SLA protection"

        approved.append({**action, "target_instances": target if target is not None else current,
                         "safety_reason": "all deterministic guardrails passed"})

    # Exactly one capacity-changing action can be executed per service cycle.
    capacity = [a for a in approved if a.get("action") in {"scale_up","scale_down","resize","stop_service"}]
    non_capacity = [a for a in approved if a.get("action") not in {"scale_up","scale_down","resize","stop_service"}]
    selected_pool = capacity[:1] + non_capacity[:1]
    return {"approved": selected_pool, "rejected": rejected}
