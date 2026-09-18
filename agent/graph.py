from __future__ import annotations
import time
from typing import Any
from langgraph.graph import StateGraph, START, END
from core.models import CostGuardState
from core.freshness import freshness_check
from core.policy import validate_actions
from core.store import init_db, add_observation, get_history, add_action
from core.tools import load_state, execute_action, get_state, refresh_data
from agent.llm import LLMClient

llm = LLMClient()
init_db()

def trace(state, stage, detail):
    t = list(state.get("trace", []))
    t.append({"stage":stage, "detail":detail})
    state["trace"] = t
    return state

def normalize(raw: dict) -> dict:
    # Accept the hackathon-style split JSON inputs and also a single service object.
    service = dict(raw.get("service") or {})
    service.update(raw.get("metrics") or {})
    service.update(raw.get("services") or {} if isinstance(raw.get("services"), dict) else {})
    if not service:
        services = raw.get("services")
        if isinstance(services, list) and services:
            service = dict(services[0])
    traffic = raw.get("traffic") or raw.get("traffic_history") or []
    if isinstance(traffic, dict):
        traffic = traffic.get("history", [])
    service["name"] = service.get("name") or service.get("service_name") or "orders-api"
    if traffic:
        service["traffic_history"] = traffic
        service.setdefault("requests_per_minute", traffic[-1].get("requests_per_minute", 0))
    if raw.get("latest_traffic"):
        service.setdefault("latest_traffic", raw["latest_traffic"])
    if raw.get("action_result"):
        service["previous_action_result"] = raw["action_result"]
    service.setdefault("min_instances", 1)
    service.setdefault("max_instances", 10)
    service.setdefault("cost_per_instance_hour", 10.0)
    service.setdefault("estimated_hourly_cost", round(float(service.get("instances",1))*float(service["cost_per_instance_hour"]),2))
    return service

def intake_node(state: CostGuardState):
    raw = state.get("raw_input", {})
    service = normalize(raw)
    state["service"] = service
    # Load the supplied state into the simulated cloud control plane.
    load_state(service)
    # Seed SQLite with the supplied observation window so idle/trend decisions use history.
    for obs in service.get("traffic_history", []):
        seeded = dict(service)
        seeded.update(obs)
        add_observation(service["name"], seeded)
    add_observation(service["name"], service)
    state["history"] = get_history(service["name"], 10)
    return trace(state, "1. Intake & Normalization", {
        "status":"complete", "service":service["name"],
        "inputs":["natural-language request","services/metrics JSON","traffic data","action result"]
    })

def freshness_node(state: CostGuardState):
    raw = state.get("raw_input", {})
    service = state["service"]
    fresh = freshness_check(service, raw)
    state["freshness"] = fresh
    if fresh.get("stale"):
        # Refresh service data through the same mock API boundary.
        refreshed = refresh_data(service, raw.get("latest_traffic") or {})
        if refreshed.get("service"):
            state["service"] = refreshed["service"]
            state["freshness"]["refresh_attempted"] = True
            state["freshness"]["refresh_result"] = "fresh data fetched"
            # Re-check after refresh.
            state["freshness_after_refresh"] = freshness_check(state["service"], {
                "current_time": raw.get("current_time"),
                "latest_traffic": {"timestamp": state["service"].get("timestamp")}
            })
            state["freshness"]["original_stale"] = True
    return trace(state, "2. Freshness Checker", state["freshness"])

def diagnostic_node(state: CostGuardState):
    service = state["service"]
    history = state.get("history", [])
    diagnosis = llm.diagnose(state["request"], service, history, state.get("freshness", {}))
    # If the original observation was stale/contradicted, explicitly prohibit cost reductions
    # during this cycle; protective action or no_action remains available.
    if state.get("freshness", {}).get("original_stale"):
        diagnosis["candidate_actions"] = [
            a for a in diagnosis.get("candidate_actions", [])
            if a.get("action") in {"scale_up","no_action"}
        ] or [{"action":"no_action","target_instances":service.get("instances"),"reason":"Original data was stale; conservative branch."}]
        diagnosis["stale_data_note"] = "Original observation was not trusted; only protective/no-action candidates remain."
    state["diagnosis"] = diagnosis
    state["candidate_actions"] = diagnosis.get("candidate_actions", [])
    state["llm_mode"] = llm.last_mode
    return trace(state, "3. Diagnostic Agent (LLM)", {
        "root_cause":diagnosis.get("root_cause"),
        "evidence":diagnosis.get("evidence",[]),
        "candidate_actions":state["candidate_actions"],
        "llm_mode":llm.last_mode
    })

def safety_node(state: CostGuardState):
    result = validate_actions(
        state["service"], state.get("freshness", {}),
        state.get("candidate_actions", []), state.get("history", [])
    )
    state["approved_actions"] = result["approved"]
    state["rejected_actions"] = result["rejected"]
    return trace(state, "4. Policy / Safety Engine", {
        "approved":result["approved"], "rejected":result["rejected"],
        "rules":["capacity bounds","latency protection","health gate","idle/history evidence",
                 "staleness gate","one capacity-changing action per cycle"]
    })

def decision_node(state: CostGuardState):
    decision = llm.choose(state["request"], state["service"], state["diagnosis"], state.get("approved_actions", []))
    # Hard stop: never allow a decision outside the approved set.
    approved = state.get("approved_actions", [])
    if approved and decision.get("action") not in {a.get("action") for a in approved}:
        decision = {"action":"no_action","target_instances":state["service"].get("instances"),
                    "justification":"LLM selection was outside the safety-approved set; deterministic veto applied."}
    if not approved:
        decision = {"action":"no_action","target_instances":state["service"].get("instances"),
                    "justification":"No candidate passed the deterministic safety engine."}
    state["decision"] = decision
    return trace(state, "5. Decision Agent (LLM)", {
        "chosen_action":decision, "llm_mode":llm.last_mode,
        "safety_approved_count":len(approved)
    })

def execution_node(state: CostGuardState):
    service = state["service"]
    decision = state["decision"]
    before = dict(service)
    if decision.get("action") == "no_action":
        result = {"status":"not_executed","error":None,"message":"No action selected.",
                  "before":before,"after":before,
                  "cost_before":before.get("estimated_hourly_cost",0),
                  "cost_after":before.get("estimated_hourly_cost",0)}
    else:
        result = execute_action(service["name"], decision)
    # Failure recovery: re-evaluate using deterministic rules and try a smaller safe scale-up.
    recovery = None
    first_failure = None
    if result.get("status") == "failed":
        first_failure = {"error": result.get("error"), "message": result.get("message")}
        if result.get("error") in {"capacity_unavailable","timeout","service_unavailable"} and decision.get("action") == "scale_up":
            current = int(before.get("instances",1))
            minimum_retry = max(current+1, int(decision.get("target_instances",current))-1)
            candidates = [{"action":"scale_up","target_instances":minimum_retry,
                           "reason":"Recovery retry after execution failure; smaller safe increase."}]
            approved_retry = validate_actions(before, state.get("freshness",{}), candidates, state.get("history",[]))["approved"]
            if approved_retry:
                recovery = execute_action(service["name"], approved_retry[0])
                if recovery.get("status") == "success":
                    first_error = result.get("error")
                    result = recovery
                    result["recovered_from"] = {"error":first_error, "first_attempt": True}
        if result.get("status") == "failed":
            result["recovery"] = "escalate"
    state["execution"] = result
    state["execution"]["recovery_attempted"] = bool(recovery)
    state["execution"]["first_failure"] = first_failure
    add_action(service["name"], decision, result)
    return trace(state, "6. Execution Agent", {
        "status":result.get("status"), "error":result.get("error"),
        "first_failure":first_failure, "recovery_attempted":bool(recovery), "message":result.get("message")
    })

def verification_node(state: CostGuardState):
    service_name = state["service"]["name"]
    time.sleep(0.4)
    after = get_state(service_name)
    before = state["execution"].get("before", state["service"])
    decision = state["decision"]
    exec_status = state["execution"].get("status")
    max_latency = float(after.get("max_latency_ms",300))
    latency_ok = float(after.get("latency_ms",0)) <= max_latency
    healthy_ok = bool(after.get("healthy",True))
    changed = after.get("instances") != before.get("instances")
    cost_before = float(state["execution"].get("cost_before", before.get("estimated_hourly_cost",0)) or 0)
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
        "status":status, "before_instances":before.get("instances"), "after_instances":after.get("instances"),
        "before_latency_ms":before.get("latency_ms"), "after_latency_ms":after.get("latency_ms"),
        "latency_within_limit":latency_ok, "healthy":healthy_ok, "state_changed":changed,
        "cost_before":round(cost_before,2), "cost_after":round(cost_after,2),
        "estimated_hourly_saving":round(cost_before-cost_after,2),
        "recovery":state["execution"].get("recovery_attempted",False)
    }
    state["verification"] = verification
    add_observation(service_name, after)
    return trace(state, "7. Verification Agent", verification)

def response_node(state: CostGuardState):
    response = llm.compose(state["request"], state["service"], state["diagnosis"], state["decision"],
                           state["execution"], state["verification"])
    state["response"] = response
    state["llm_mode"] = llm.last_mode
    return trace(state, "8. Response Composer (LLM)", {"response":response, "llm_mode":llm.last_mode})

def build_graph():
    g = StateGraph(CostGuardState)
    g.add_node("intake", intake_node)
    g.add_node("freshness", freshness_node)
    g.add_node("diagnostic", diagnostic_node)
    g.add_node("safety", safety_node)
    g.add_node("decision", decision_node)
    g.add_node("execution", execution_node)
    g.add_node("verification", verification_node)
    g.add_node("response", response_node)
    g.add_edge(START, "intake")
    g.add_edge("intake", "freshness")
    g.add_edge("freshness", "diagnostic")
    g.add_edge("diagnostic", "safety")
    g.add_edge("safety", "decision")
    g.add_edge("decision", "execution")
    g.add_edge("execution", "verification")
    g.add_edge("verification", "response")
    g.add_edge("response", END)
    return g.compile()

graph = build_graph()

def run_costguard(request: str, raw_input: dict) -> dict:
    return graph.invoke({"request":request, "raw_input":raw_input, "trace":[]})
