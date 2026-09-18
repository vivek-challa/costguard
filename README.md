# CostGuard — Autonomous Cloud Cost-Optimization Agent

CostGuard is a hackathon MVP aligned to the supplied P3 problem statement. It uses:
- Streamlit interface
- Python + FastAPI
- LangGraph orchestration
- SQLite state/memory
- Groq API OR local Ollama for LLM reasoning
- Mock Cloud Control API

## What is real in this MVP
1. Natural-language request + JSON cloud state
2. 8-stage LangGraph workflow
3. LLM diagnosis, action selection and response composition
4. Deterministic freshness and safety gates
5. Mock API execution with injectable failures
6. SQLite rolling history
7. Before/after verification
8. Cost impact calculation
9. Explicit no_action, stale-data and failure-recovery branches
10. Full stage-by-stage trace in Streamlit

## Project structure
- `app.py` — Streamlit UI
- `agent/graph.py` — LangGraph workflow
- `agent/llm.py` — Groq/Ollama adapter
- `core/policy.py` — deterministic safety engine
- `core/freshness.py` — deterministic freshness checker
- `core/store.py` — SQLite memory/state
- `core/tools.py` — client for mock cloud API
- `backend/main.py` — FastAPI mock Cloud Control API
- `data/scenarios/` — four judge-ready test scenarios
- `docs/TECH_STACK_AND_WORKING.docx` — judge/team technical guide

## 1. Install Python
Use Python 3.10+.

## 2. Create environment
Windows CMD:
```bat
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

PowerShell:
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## 3. Configure the LLM
Copy `.env.example` to `.env`.

### Option A — Groq
Set:
```text
LLM_PROVIDER=groq
GROQ_API_KEY=YOUR_KEY
GROQ_MODEL=llama-3.3-70b-versatile
```
The key is read only by `agent/llm.py`. Do not paste it into the Streamlit UI or source code.

### Option B — Ollama
Install Ollama and pull a model:
```bat
ollama pull llama3.2
```
Then set:
```text
LLM_PROVIDER=ollama
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=llama3.2
```
No API key is needed.

## 4. Start the Mock Cloud Control API
Terminal 1:
```bat
.venv\Scripts\activate
uvicorn backend.main:app --reload --port 8000
```

## 5. Start Streamlit
Terminal 2:
```bat
.venv\Scripts\activate
streamlit run app.py
```

Open the Streamlit URL shown in the terminal, normally `http://localhost:8501`.

## 6. Run the judge demo
Load one of:
- `data/scenarios/test_a_cost_optimization.json`
- `data/scenarios/test_b_rising_traffic.json`
- `data/scenarios/test_c_stale_observation.json`
- `data/scenarios/test_d_failed_action.json`

Recommended order:
1. Test A — proves cost optimization
2. Test B — proves safety beats blind cost cutting
3. Test C — proves stale data is blocked
4. Test D — proves failure recovery

The UI has a scenario loader. It sends the JSON state to the same workflow the judge can watch.

## Where each architecture item lives
1. Intake & Normalization → `agent/graph.py: intake_node`
2. Freshness Checker → `agent/graph.py: freshness_node` + `core/freshness.py`
3. Diagnostic Agent → `agent/graph.py: diagnostic_node`
4. Policy / Safety Engine → `agent/graph.py: safety_node` + `core/policy.py`
5. Decision Agent → `agent/graph.py: decision_node`
6. Execution Agent → `agent/graph.py: execution_node` + `core/tools.py`
7. Verification Agent → `agent/graph.py: verification_node`
8. Response Composer → `agent/graph.py: response_node`
9. Memory / State Store → `core/store.py`
10. Mock Cloud Control API → `backend/main.py`
11. Streamlit → `app.py`

## Important implementation detail
The eight stages are logical responsibilities, not eight separate model calls. Diagnosis, decision and response use the LLM; freshness, safety, execution and verification have deterministic controls. This matches the supplied solution design.

## Troubleshooting
- `ModuleNotFoundError`: activate `.venv` and run `pip install -r requirements.txt`.
- Groq error: check `GROQ_API_KEY`, model name, and internet connection.
- Ollama error: make sure Ollama is running and the selected model exists.
- API connection error: start FastAPI on port 8000 before Streamlit.
- Port busy: use another FastAPI port and change `CLOUD_API_URL` in `.env`.
- If the LLM is unavailable, the demo automatically uses a deterministic fallback so the safety/execution workflow can still be demonstrated. The UI clearly labels fallback mode.

## Reset demo state
Delete `costguard.db` and restart the app. It is recreated automatically.
