from __future__ import annotations
import json
import os
import re
import urllib.request
from dotenv import load_dotenv

load_dotenv()

class LLMClient:
    def __init__(self):
        self.provider = os.getenv("LLM_PROVIDER", "groq").lower().strip()
        self.groq_key = os.getenv("GROQ_API_KEY", "")
        self.groq_model = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
        self.ollama_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")
        self.ollama_model = os.getenv("OLLAMA_MODEL", "llama3.2")
        self.last_mode = "unknown"

    def _post_json(self, url: str, payload: dict, headers: dict | None = None) -> dict:
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers={"Content-Type":"application/json", **(headers or {})}, method="POST")
        with urllib.request.urlopen(req, timeout=45) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def chat(self, system: str, user: str) -> str:
        try:
            if self.provider == "ollama":
                out = self._post_json(
                    f"{self.ollama_url}/api/chat",
                    {"model": self.ollama_model,
                     "messages":[{"role":"system","content":system},{"role":"user","content":user}],
                     "stream":False, "options":{"temperature":0.1}}
                )
                self.last_mode = f"Ollama: {self.ollama_model}"
                return out["message"]["content"]
            if not self.groq_key or self.groq_key.startswith("PASTE_"):
                raise RuntimeError("GROQ_API_KEY is not configured")
            out = self._post_json(
                "https://api.groq.com/openai/v1/chat/completions",
                {"model":self.groq_model,"temperature":0.1,
                 "messages":[{"role":"system","content":system},{"role":"user","content":user}]},
                {"Authorization":f"Bearer {self.groq_key}"}
            )
            self.last_mode = f"Groq: {self.groq_model}"
            return out["choices"][0]["message"]["content"]
        except Exception as exc:
            self.last_mode = f"Deterministic fallback ({type(exc).__name__})"
            return ""

    @staticmethod
    def extract_json(text: str) -> dict:
        if not text:
            return {}
        cleaned = text.strip().replace("```json", "").replace("```", "").strip()
        try:
            return json.loads(cleaned)
        except Exception:
            match = re.search(r"\{.*\}", cleaned, re.DOTALL)
            if match:
                try:
                    return json.loads(match.group(0))
                except Exception:
                    return {}
        return {}

    def diagnose(self, request: str, service: dict, history: list[dict], freshness: dict) -> dict:
        system = '''You are CostGuard Diagnostic Agent. Analyze cloud cost and reliability signals.
Return ONLY JSON with keys: root_cause, evidence, candidate_actions.
candidate_actions is a list of objects with action, target_instances, reason.
Allowed actions: scale_up, scale_down, resize, stop_service, delay_batch, no_action.
Do not claim an action is safe; safety is checked separately by deterministic code.'''
        prompt = json.dumps({"request":request,"service":service,"history":history[-5:],"freshness":freshness}, indent=2)
        parsed = self.extract_json(self.chat(system, prompt))
        if parsed:
            return parsed
        return deterministic_diagnosis(service, history, freshness)

    def choose(self, request: str, service: dict, diagnosis: dict, approved: list[dict]) -> dict:
        system = '''You are CostGuard Decision Agent. Pick exactly one action from the APPROVED list.
Return ONLY JSON: {"action":"...","target_instances":0,"justification":"..."}.
Never invent an action outside the approved list. Prefer protecting latency and health over cost savings.'''
        prompt = json.dumps({"request":request,"service":service,"diagnosis":diagnosis,"approved_actions":approved}, indent=2)
        parsed = self.extract_json(self.chat(system, prompt))
        if parsed and parsed.get("action") in {a.get("action") for a in approved}:
            return parsed
        if approved:
            a = approved[0]
            return {"action":a["action"], "target_instances":a.get("target_instances"),
                    "justification":a.get("reason","Selected from safety-approved set.")}
        return {"action":"no_action","target_instances":service.get("instances"),
                "justification":"No safety-approved action is available."}

    def compose(self, request: str, service: dict, diagnosis: dict, decision: dict, execution: dict, verification: dict) -> str:
        system = '''You are CostGuard Response Composer. Write a concise audit-friendly response.
Mention observed problem, action taken or withheld, execution status, verification result, and estimated hourly cost impact.
Never say an action succeeded unless verification says verified.'''
        prompt = json.dumps({"request":request,"service":service,"diagnosis":diagnosis,"decision":decision,
                             "execution":execution,"verification":verification}, indent=2)
        text = self.chat(system, prompt)
        if text:
            return text.strip()
        return deterministic_response(service, decision, execution, verification)

def deterministic_diagnosis(service, history, freshness):
    rpm = float(service.get("requests_per_minute",0))
    cpu = float(service.get("cpu_percent",0))
    latency = float(service.get("latency_ms",0))
    max_latency = float(service.get("max_latency_ms",300))
    current = int(service.get("instances",1))
    min_i = int(service.get("min_instances",1))
    max_i = int(service.get("max_instances",10))
    evidence, candidates = [], []
    if freshness.get("stale"):
        return {"root_cause":"Untrusted or stale observation data","evidence":freshness.get("reasons",[]),
                "candidate_actions":[{"action":"no_action","target_instances":current,"reason":"Wait for fresh data."}]}
    if latency >= max_latency * 0.85 or cpu >= 80 or (len(history)>=2 and rpm > float(history[-2].get("requests_per_minute",rpm))*1.5):
        evidence.append(f"latency={latency:.0f}ms, CPU={cpu:.0f}%, traffic={rpm:.0f} rpm")
        target = min(max_i, max(current+2, current+1))
        candidates.append({"action":"scale_up","target_instances":target,"reason":"Protect latency/SLA under load."})
    if rpm <= 1 and cpu < 20 and current > min_i:
        evidence.append("near-zero traffic with low CPU and spare instances")
        candidates.append({"action":"scale_down","target_instances":min_i,"reason":"Reduce idle capacity after history confirms low traffic."})
    if not candidates:
        candidates.append({"action":"no_action","target_instances":current,"reason":"No clear safe optimization signal."})
    return {"root_cause":"; ".join(evidence) if evidence else "No urgent cost/reliability anomaly detected",
            "evidence":evidence or ["Current utilization and traffic are within normal range."],
            "candidate_actions":candidates}

def deterministic_response(service, decision, execution, verification):
    cost_before = float(execution.get("cost_before", service.get("estimated_hourly_cost",0)) or 0)
    cost_after = float(verification.get("cost_after", cost_before) or cost_before)
    saving = cost_before - cost_after
    return (f"{service.get('name','service')}: {decision.get('justification','No safe action available.')} "
            f"Action={decision.get('action','no_action')}. Execution={execution.get('status','not executed')}. "
            f"Verification={verification.get('status','unknown')}. Estimated hourly cost impact=${saving:.2f}.")
