import json
from pathlib import Path
import urllib.request
import streamlit as st
from dotenv import load_dotenv
from agent.graph import run_costguard

load_dotenv()

st.set_page_config(page_title="CostGuard", page_icon="☁️", layout="wide")

st.title("CostGuard")
st.caption("Autonomous Cloud Cost-Optimization Agent  •  Investigate → Decide → Act Safely → Verify → Explain")

scenario_dir = Path(__file__).resolve().parent / "data" / "scenarios"
scenarios = {
    "Test A — Cost optimization": "test_a_cost_optimization.json",
    "Test B — Rising traffic": "test_b_rising_traffic.json",
    "Test C — Stale observation": "test_c_stale_observation.json",
    "Test D — Failed action recovery": "test_d_failed_action.json",
}

with st.sidebar:
    st.header("Demo Controls")
    selected = st.selectbox("Judge scenario", list(scenarios))
    if st.button("Load selected scenario"):
        data = json.loads((scenario_dir/scenarios[selected]).read_text(encoding="utf-8"))
        st.session_state["request"] = data.pop("request")
        st.session_state["payload"] = json.dumps(data, indent=2)
        st.rerun()
    st.divider()
    st.write("LLM is used for diagnosis, action selection and response composition.")
    st.write("Safety, freshness, execution and verification contain deterministic controls.")

default_request = "Reduce cloud cost without compromising performance, reliability or SLA."
default_payload = json.dumps(json.loads((scenario_dir/scenarios["test_a_cost_optimization.json"]).read_text()), indent=2)
request = st.text_area("Natural-language request", st.session_state.get("request", default_request), height=90)
payload_text = st.text_area("Cloud state JSON", st.session_state.get("payload", default_payload), height=430)

col1, col2 = st.columns([1,4])
with col1:
    run = st.button("▶ Run CostGuard", type="primary", use_container_width=True)
with col2:
    st.info("Tip: run A → B → C → D in that order for the strongest 4-branch demo.")

if run:
    try:
        raw = json.loads(payload_text)
    except json.JSONDecodeError as e:
        st.error(f"Invalid JSON: {e}")
        st.stop()

    with st.spinner("CostGuard is investigating, applying guardrails, executing and verifying..."):
        try:
            result = run_costguard(request, raw)
        except Exception as e:
            st.error(f"Workflow error: {e}")
            st.exception(e)
            st.stop()

    st.success("Workflow completed")
    c1,c2,c3,c4 = st.columns(4)
    verification = result.get("verification", {})
    execution = result.get("execution", {})
    c1.metric("Action", result.get("decision",{}).get("action","no_action"))
    c2.metric("Verification", verification.get("status","unknown"))
    c3.metric("Hourly cost", f"${verification.get('cost_after',0):.2f}")
    c4.metric("Estimated saving", f"${verification.get('estimated_hourly_saving',0):.2f}")

    st.subheader("Response to User")
    st.write(result.get("response",""))

    st.subheader("Before → After Evidence")
    before = execution.get("before", {})
    after = {"instances":verification.get("after_instances"),
             "latency_ms":verification.get("after_latency_ms"),
             "healthy":verification.get("healthy"),
             "estimated_hourly_cost":verification.get("cost_after")}
    evidence = {
        "Metric":["Instances","Latency (ms)","Healthy","Estimated hourly cost"],
        "Before":[before.get("instances"),before.get("latency_ms"),before.get("healthy"),verification.get("cost_before")],
        "After":[after.get("instances"),after.get("latency_ms"),after.get("healthy"),after.get("estimated_hourly_cost")]
    }
    st.table(evidence)

    st.subheader("Agent Audit Trace")
    for item in result.get("trace", []):
        with st.expander(item["stage"], expanded=True):
            detail = item["detail"]
            if isinstance(detail, (dict,list)):
                st.json(detail)
            else:
                st.write(detail)

    with st.expander("Full final state"):
        st.json(result)
