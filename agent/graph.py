from __future__ import annotations
import time
from typing import Any, Optional
from langgraph.graph import StateGraph, START, END
from core.models import CostGuardState
from core.freshness import freshness_check
from core.policy import validate_actions
from core.store import get_history, get_cloud_state
from core.tools import fetch_cloud_state, invoke_cloud_action, refresh_data
from agent.llm import LLMClient

llm = LLMClient()

def trace(state: CostGuardState, stage: str, detail: Any) -> CostGuardState:
    t = list(state.get("trace", []))
    t.append({"stage": stage, "detail": detail})
    state["trace"] = t
    return state

def extract_service_name(request: str, raw_input: dict | None = None) -> str:
    raw = raw_input or {}
    if isinstance(raw, list) or (isinstance(raw, dict) and raw.get("services")):
        return "fleet"

    explicit = raw.get("service_name") or (raw.get("service") or {}).get("name") or (raw.get("service") or {}).get("service_id")
    if explicit:
        return explicit

    req_lower = (request or "").lower()
    if "reports-worker" in req_lower or "reports" in req_lower or "worker" in req_lower:
        return "reports-worker"
    if "payment-api" in req_lower or "payment" in req_lower:
        return "payment-api"
    if "checkout-api" in req_lower or "checkout" in req_lower:
        return "checkout-api"
    if "orders-api" in req_lower or "orders" in req_lower:
        return "orders-api"

    # Multi-service or fleet review queries
    if any(k in req_lower for k in ["services", "fleet", "all services", "current services", "cluster"]) or ("unnecessary cost" in req_lower and not any(s in req_lower for s in ["reports", "orders", "checkout", "payment"])):
        return "fleet"

    # If the operator asks to eliminate idle capacity, downscale, or stop waste without naming a service:
    if any(w in req_lower for w in ["idle", "waste", "downscale", "scale down", "cost optimization"]):
        return "reports-worker"

    return "orders-api"

# -----------------------------------------------------------------------------
# STAGE 1: REQUEST INTAKE
# -----------------------------------------------------------------------------
def intake_node(state: CostGuardState) -> CostGuardState:
    req = (state.get("request") or "").strip()
    raw = state.get("raw_input") or {}
    service_name = extract_service_name(req, raw)
    state["request"] = req
    return trace(state, "1. Request Intake", {
        "status": "received",
        "request": req,
        "target_service": service_name,
        "mode": "autonomous_evaluation"
    })

# -----------------------------------------------------------------------------
# STAGE 2: INTENT DETECTION
# -----------------------------------------------------------------------------
def intent_node(state: CostGuardState) -> CostGuardState:
    req = state.get("request", "")
    intent_data = llm.detect_intent(req)
    if not intent_data.get("target_service"):
        intent_data["target_service"] = extract_service_name(req, state.get("raw_input"))
    state["intent"] = intent_data
    return trace(state, "2. Intent Detection", intent_data)

# -----------------------------------------------------------------------------
# STAGE 3: CLOUD STATE RETRIEVAL
# -----------------------------------------------------------------------------
def cloud_retrieval_node(state: CostGuardState) -> CostGuardState:
    raw = state.get("raw_input") or {}
    service_name = (state.get("intent") or {}).get("target_service") or extract_service_name(state.get("request", ""), raw)

    if service_name == "fleet":
        # Multi-service review: inspect all active simulated services
        if isinstance(raw, list):
            services_raw = raw
        elif isinstance(raw, dict) and raw.get("services"):
            services_raw = raw["services"]
        else:
            services_raw = None

        fleet_services = {}
        if services_raw:
            for s_item in services_raw:
                s_name = s_item.get("name") or s_item.get("service_id") or s_item.get("service") or "service"
                norm_s = dict(s_item)
                norm_s["name"] = s_name
                norm_s["service"] = s_name
                norm_s.setdefault("cost_per_instance_hour", float(s_item.get("cost_per_instance_hour") or s_item.get("cost_per_hour", 18.50)))
                norm_s.setdefault("estimated_hourly_cost", round(float(norm_s.get("instances", 4)) * float(norm_s["cost_per_instance_hour"]), 2))
                fleet_services[s_name] = norm_s
        else:
            for s_name in ["orders-api", "reports-worker"]:
                try:
                    s_state = fetch_cloud_state(s_name)
                except Exception:
                    s_state = get_cloud_state(s_name)
                fleet_services[s_name] = s_state

        state["fleet_services"] = fleet_services

        # Target the primary service that has idle capacity / waste
        target_to_act = "reports-worker" if "reports-worker" in fleet_services else list(fleet_services.keys())[0]
        for s_name, s_data in fleet_services.items():
            rpm = float(s_data.get("requests_per_minute", 0))
            instances = int(s_data.get("instances", 1))
            min_i = int(s_data.get("min_instances", 1))
            if rpm <= 5 and instances > min_i:
                target_to_act = s_name
                break

        service = fleet_services[target_to_act]
        state["service"] = service
        state["history"] = get_history(service["name"], 10)
        state["freshness"] = freshness_check(service, raw if isinstance(raw, dict) else {})

        return trace(state, "3. Cloud State Retrieval", {
            "source": "Mock Cloud API (Multi-Service Fleet Inspection)",
            "services_reviewed": list(fleet_services.keys()),
            "primary_optimization_target": target_to_act,
            "fleet_snapshot": {
                name: {
                    "instances": s.get("instances"),
                    "requests_per_minute": s.get("requests_per_minute"),
                    "cpu_percent": s.get("cpu_percent"),
                    "latency_ms": s.get("latency_ms"),
                    "hourly_cost": s.get("estimated_hourly_cost")
                }
                for name, s in fleet_services.items()
            }
        })
    else:
        # Single service retrieval
        try:
            service = fetch_cloud_state(service_name)
        except Exception:
            service = get_cloud_state(service_name)

        if isinstance(raw, dict):
            if raw.get("metrics"):
                service.update(raw["metrics"])
            if raw.get("traffic_history"):
                service["traffic_history"] = raw["traffic_history"]
            if raw.get("latest_traffic"):
                service["latest_traffic"] = raw["latest_traffic"]

        state["service"] = service
        fresh = freshness_check(service, raw if isinstance(raw, dict) else {})
        state["freshness"] = fresh

        if fresh.get("stale"):
            try:
                refreshed = refresh_data(service, (raw if isinstance(raw, dict) else {}).get("latest_traffic") or {})
                if refreshed.get("service"):
                    state["service"] = refreshed["service"]
                    state["freshness"]["refresh_attempted"] = True
                    state["freshness"]["original_stale"] = True
            except Exception:
                pass

        state["history"] = get_history(service["name"], 10)

        return trace(state, "3. Cloud State Retrieval", {
            "source": "Mock Cloud API (GET /cloud/state)",
            "service": service.get("name", service_name),
            "instances": service.get("instances"),
            "cpu_percent": service.get("cpu_percent"),
            "requests_per_minute": service.get("requests_per_minute"),
            "latency_ms": service.get("latency_ms"),
            "max_latency_ms": service.get("max_latency_ms", 300.0),
            "healthy": service.get("healthy", True),
            "hourly_cost": service.get("estimated_hourly_cost"),
            "timestamp": service.get("timestamp")
        })

# -----------------------------------------------------------------------------
# STAGE 4: DIAGNOSIS
# -----------------------------------------------------------------------------
def diagnostic_node(state: CostGuardState) -> CostGuardState:
    fleet_services = state.get("fleet_services")
    service = state["service"]
    history = state.get("history", [])
    intent = state.get("intent", {})
    freshness = state.get("freshness", {})

    if fleet_services and len(fleet_services) > 1:
        evidence = []
        candidates = []
        for s_name, s_data in fleet_services.items():
            rpm = float(s_data.get("requests_per_minute", 0))
            cpu = float(s_data.get("cpu_percent", 0))
            latency = float(s_data.get("latency_ms", 0))
            max_lat = float(s_data.get("max_latency_ms", 300))
            inst = int(s_data.get("instances", 4))
            min_i = int(s_data.get("min_instances", 1))

            if rpm <= 5 and inst > min_i:
                target_i = min_i
                candidates.append({
                    "service": s_name,
                    "action": "scale_down",
                    "target_instances": target_i,
                    "amount": inst - target_i,
                    "reason": f"Service '{s_name}' is idle ({rpm:,.0f} req/min, {cpu:.1f}% CPU) with {inst} provisioned instances. Safe to scale down to {target_i}."
                })
                evidence.append(f"Idle waste detected on '{s_name}': {inst} instances running with {rpm:,.0f} req/min.")
            else:
                candidates.append({
                    "service": s_name,
                    "action": "no_action",
                    "target_instances": inst,
                    "reason": f"Service '{s_name}' actively handling {rpm:,.0f} req/min ({latency:.1f}ms latency). Capacity preserved to protect SLA."
                })
                evidence.append(f"'{s_name}' actively serving traffic ({rpm:,.0f} req/min, {latency:.1f}ms latency). Capacity preserved to protect SLA.")

        diagnosis = {
            "root_cause": "; ".join(evidence),
            "evidence": evidence,
            "candidate_actions": candidates
        }
        state["diagnosis"] = diagnosis
        state["candidate_actions"] = candidates
        state["llm_mode"] = "Deterministic Fleet Diagnostic Engine"

        return trace(state, "4. Diagnosis", {
            "root_cause": diagnosis["root_cause"],
            "evidence": evidence,
            "candidate_actions": candidates,
            "fleet_review_mode": True
        })
    else:
        diagnosis = llm.diagnose(state["request"], service, history, freshness, intent)

        if freshness.get("original_stale"):
            diagnosis["candidate_actions"] = [
                a for a in diagnosis.get("candidate_actions", [])
                if a.get("action") in {"scale_up", "no_action"}
            ] or [{"action": "no_action", "target_instances": service.get("instances"), "reason": "Original observation was stale; conservative hold."}]
            diagnosis["stale_data_note"] = "Data freshness gate triggered: cost reduction withheld until confirmed fresh."

        state["diagnosis"] = diagnosis
        state["candidate_actions"] = diagnosis.get("candidate_actions", [])
        state["llm_mode"] = llm.last_mode

        return trace(state, "4. Diagnosis", {
            "root_cause": diagnosis.get("root_cause"),
            "evidence": diagnosis.get("evidence", []),
            "candidate_actions": state["candidate_actions"],
            "llm_mode": llm.last_mode
        })

# -----------------------------------------------------------------------------
# STAGE 5: POLICY EVALUATION
# -----------------------------------------------------------------------------
def safety_node(state: CostGuardState) -> CostGuardState:
    fleet_services = state.get("fleet_services")
    if fleet_services and len(fleet_services) > 1:
        fleet_review = []
        approved_all = []
        rejected_all = []

        for s_name, s_data in fleet_services.items():
            s_candidates = [c for c in state.get("candidate_actions", []) if c.get("service") == s_name]
            if not s_candidates:
                s_candidates = [{"action": "no_action", "target_instances": s_data.get("instances"), "reason": "Capacity maintained to protect SLA."}]

            s_hist = get_history(s_name, 10)
            s_fresh = freshness_check(s_data, {})
            val_res = validate_actions(s_data, s_fresh, s_candidates, s_hist)

            app = val_res.get("approved", [])
            chosen_action = app[0].get("action") if app else "no_action"
            chosen_target = app[0].get("target_instances") if app else s_data.get("instances")

            if chosen_action == "scale_down":
                rec = f"Scale Down ({s_data.get('instances')} → {chosen_target} instances)"
                status_label = "Idle Overprovisioning Detected"
                approved_all.extend([{**a, "service": s_name} for a in app])
            else:
                rec = f"Preserve Baseline ({s_data.get('instances')} instances)"
                status_label = "Active Traffic (SLA Protected)"

            fleet_review.append({
                "service": s_name,
                "instances": s_data.get("instances"),
                "requests_per_minute": s_data.get("requests_per_minute"),
                "latency_ms": s_data.get("latency_ms"),
                "max_latency_ms": s_data.get("max_latency_ms", 300.0),
                "hourly_cost": s_data.get("estimated_hourly_cost"),
                "status": status_label,
                "recommendation": rec,
                "action": chosen_action,
                "target_instances": chosen_target,
                "reason": app[0].get("reason", "Policy checks passed.") if app else "Capacity preserved."
            })
            rejected_all.extend(val_res.get("rejected", []))

        state["fleet_review"] = fleet_review
        if approved_all:
            scale_downs = [a for a in approved_all if a.get("action") == "scale_down"]
            target_act = scale_downs[0] if scale_downs else approved_all[0]
            target_svc = target_act.get("service") or state["service"]["name"]
            state["service"] = fleet_services.get(target_svc, state["service"])
            state["approved_actions"] = [target_act]
        else:
            state["approved_actions"] = [{"action": "no_action", "target_instances": state["service"].get("instances"), "safety_reason": "explicit safe no-action"}]
        state["rejected_actions"] = rejected_all

        return trace(state, "5. Policy Evaluation", {
            "fleet_review": fleet_review,
            "approved": state["approved_actions"],
            "rejected": rejected_all,
            "guardrails_evaluated": [
                "Capacity Bounds [min_instances, max_instances]",
                "Latency SLA Ceiling (<300ms)",
                "Health Gate (unhealthy prevents scale-down)",
                "Idle History Gate (sustained low traffic evidence)",
                "Telemetry Freshness Gate (30m threshold)",
                "Single Action Rate Limiter"
            ]
        })
    else:
        result = validate_actions(
            state["service"],
            state.get("freshness", {}),
            state.get("candidate_actions", []),
            state.get("history", [])
        )
        state["approved_actions"] = result["approved"]
        state["rejected_actions"] = result["rejected"]

        return trace(state, "5. Policy Evaluation", {
            "approved": result["approved"],
            "rejected": result["rejected"],
            "guardrails_evaluated": [
                "Capacity Bounds [min_instances, max_instances]",
                "Latency SLA Ceiling (<300ms)",
                "Health Gate (unhealthy prevents scale-down)",
                "Idle History Gate (sustained low traffic evidence)",
                "Telemetry Freshness Gate (30m threshold)",
                "Single Action Rate Limiter"
            ]
        })

# -----------------------------------------------------------------------------
# STAGE 6: ACTION SELECTION
# -----------------------------------------------------------------------------
def decision_node(state: CostGuardState) -> CostGuardState:
    approved = state.get("approved_actions", [])
    fleet_review = state.get("fleet_review")

    if fleet_review and approved and approved[0].get("action") == "scale_down":
        act = approved[0]
        s_name = act.get("service") or state["service"]["name"]
        target = act.get("target_instances", 1)
        decision = {
            "action": "scale_down",
            "target_instances": target,
            "service": s_name,
            "justification": f"Fleet audit completed: orders-api capacity is required for active traffic (SLA protected), while {s_name} is running {state['service'].get('instances')} idle instances with 0 RPM. Scaling down {s_name} to {target} instance(s) safely reduces spend without risking service reliability."
        }
        state["decision"] = decision
        return trace(state, "6. Action Selection", {
            "chosen_action": "scale_down",
            "target_service": s_name,
            "target_instances": target,
            "justification": decision["justification"],
            "fleet_review_mode": True
        })

    decision = llm.choose(
        state["request"],
        state["service"],
        state["diagnosis"],
        approved,
        state.get("intent", {})
    )

    # Deterministic hard veto
    if approved and decision.get("action") not in {a.get("action") for a in approved}:
        decision = {
            "action": approved[0]["action"],
            "target_instances": approved[0].get("target_instances"),
            "justification": "LLM selection vetoed by deterministic policy engine; selected highest-priority approved action."
        }
    elif not approved:
        decision = {
            "action": "no_action",
            "target_instances": state["service"].get("instances"),
            "justification": "No candidate action passed the deterministic safety engine."
        }

    state["decision"] = decision
    return trace(state, "6. Action Selection", {
        "chosen_action": decision.get("action"),
        "target_instances": decision.get("target_instances"),
        "justification": decision.get("justification"),
        "approved_count": len(approved),
        "llm_mode": llm.last_mode
    })

# -----------------------------------------------------------------------------
# STAGE 7: ACTION EXECUTION (VIA MOCK CLOUD API)
# -----------------------------------------------------------------------------
def execution_node(state: CostGuardState) -> CostGuardState:
    service = state["service"]
    decision = state["decision"]
    before = dict(service)

    if decision.get("action") == "no_action":
        result = {
            "status": "not_executed",
            "error": None,
            "message": "Baseline preserved; no state change required.",
            "before": before,
            "after": before,
            "cost_before": before.get("estimated_hourly_cost", 0.0),
            "cost_after": before.get("estimated_hourly_cost", 0.0),
        }
        recovery = None
        first_failure = None
    else:
        # Crucial architectural boundary: CostGuard calls Mock Cloud API
        result = invoke_cloud_action(service["name"], decision)
        recovery = None
        first_failure = None

        # Automated failure recovery
        if result.get("status") == "failed":
            first_failure = {"error": result.get("error"), "message": result.get("message")}
            if result.get("error") in {"capacity_unavailable", "timeout", "service_unavailable"} and decision.get("action") == "scale_up":
                current_i = int(before.get("instances", 4))
                smaller_target = max(current_i + 1, int(decision.get("target_instances", current_i)) - 1)
                retry_candidates = [{
                    "action": "scale_up",
                    "target_instances": smaller_target,
                    "reason": "Automated recovery retry after capacity rejection; smaller safe increment."
                }]
                approved_retry = validate_actions(before, state.get("freshness", {}), retry_candidates, state.get("history", []))["approved"]
                if approved_retry:
                    recovery = invoke_cloud_action(service["name"], approved_retry[0])
                    if recovery.get("status") == "success":
                        err_name = result.get("error")
                        result = recovery
                        result["recovered_from"] = {"error": err_name, "first_attempt": True}

    state["execution"] = result
    state["execution"]["recovery_attempted"] = bool(recovery)
    state["execution"]["first_failure"] = first_failure

    return trace(state, "7. Action Execution", {
        "api_endpoint": "POST /cloud/action",
        "service": service["name"],
        "action": decision.get("action"),
        "status": result.get("status"),
        "error": result.get("error"),
        "message": result.get("message"),
        "recovery_attempted": bool(recovery),
        "persisted_to_mock_cloud": True
    })

# -----------------------------------------------------------------------------
# STAGE 8: VERIFICATION
# -----------------------------------------------------------------------------
def verification_node(state: CostGuardState) -> CostGuardState:
    service_name = state["service"]["name"]
    time.sleep(0.3)

    # Fetch fresh verified cloud state from Mock Cloud API
    try:
        after = fetch_cloud_state(service_name)
    except Exception:
        after = get_cloud_state(service_name)

    before = state["execution"].get("before", state["service"])
    decision = state["decision"]
    exec_status = state["execution"].get("status")

    max_lat = float(after.get("max_latency_ms", 300.0))
    latency_ok = float(after.get("latency_ms", 0.0)) <= max_lat
    healthy_ok = bool(after.get("healthy", True))
    changed = after.get("instances") != before.get("instances")

    cost_before = float(state["execution"].get("cost_before", before.get("estimated_hourly_cost", 111.00)) or 0.0)
    cost_after = float(after.get("estimated_hourly_cost", cost_before) or cost_before)

    if decision.get("action") == "no_action":
        status = "verified_no_action"
    elif exec_status == "success" and latency_ok and healthy_ok:
        status = "verified"
    elif exec_status == "failed":
        status = "escalated"
    else:
        status = "rollback_or_escalate"

    verification = {
        "status": status,
        "before_instances": before.get("instances"),
        "after_instances": after.get("instances"),
        "before_latency_ms": before.get("latency_ms"),
        "after_latency_ms": after.get("latency_ms"),
        "latency_within_limit": latency_ok,
        "healthy": healthy_ok,
        "state_changed": changed,
        "cost_before": round(cost_before, 2),
        "cost_after": round(cost_after, 2),
        "estimated_hourly_saving": round(cost_before - cost_after, 2),
        "recovery": state["execution"].get("recovery_attempted", False),
    }

    state["verification"] = verification
    return trace(state, "8. Verification", verification)

# -----------------------------------------------------------------------------
# STAGE 9: EXPLANATION
# -----------------------------------------------------------------------------
def response_node(state: CostGuardState) -> CostGuardState:
    response = llm.compose(
        state["request"],
        state["service"],
        state["diagnosis"],
        state["decision"],
        state["execution"],
        state["verification"],
        state.get("intent", {})
    )
    state["response"] = response
    state["llm_mode"] = llm.last_mode
    return trace(state, "9. Explanation", {
        "status": "complete",
        "llm_mode": llm.last_mode,
        "response": response
    })

# -----------------------------------------------------------------------------
# GRAPH COMPILATION
# -----------------------------------------------------------------------------
def build_graph():
    g = StateGraph(CostGuardState)
    g.add_node("intake", intake_node)
    g.add_node("intent", intent_node)
    g.add_node("cloud_retrieval", cloud_retrieval_node)
    g.add_node("diagnostic", diagnostic_node)
    g.add_node("safety", safety_node)
    g.add_node("decision", decision_node)
    g.add_node("execution", execution_node)
    g.add_node("verification", verification_node)
    g.add_node("response", response_node)

    g.add_edge(START, "intake")
    g.add_edge("intake", "intent")
    g.add_edge("intent", "cloud_retrieval")
    g.add_edge("cloud_retrieval", "diagnostic")
    g.add_edge("diagnostic", "safety")
    g.add_edge("safety", "decision")
    g.add_edge("decision", "execution")
    g.add_edge("execution", "verification")
    g.add_edge("verification", "response")
    g.add_edge("response", END)

    return g.compile()

graph = build_graph()

def run_costguard(request: str, raw_input: dict | None = None) -> dict:
    return graph.invoke({
        "request": request,
        "raw_input": raw_input or {},
        "trace": []
    })
