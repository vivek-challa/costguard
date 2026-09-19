import json
import urllib.request
import urllib.error
import os
from dotenv import load_dotenv

load_dotenv()

def api_url() -> str:
    return os.getenv("CLOUD_API_URL", "http://127.0.0.1:8000").rstrip("/")

def check_api_health() -> bool:
    try:
        req = urllib.request.Request(api_url() + "/health", method="GET")
        with urllib.request.urlopen(req, timeout=2.0) as r:
            return json.loads(r.read().decode()).get("status") == "ok"
    except Exception:
        return False

def post(path: str, payload: dict) -> dict:
    req = urllib.request.Request(
        api_url() + path,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST"
    )
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read().decode("utf-8"))

def get(path: str) -> dict:
    req = urllib.request.Request(api_url() + path, method="GET")
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read().decode("utf-8"))

# -----------------------------------------------------------------------------
# DEDICATED MOCK CLOUD API CLIENT (V2 ARCHITECTURE)
# -----------------------------------------------------------------------------

def fetch_cloud_state(service_name: str = "orders-api") -> dict:
    """Fetch active cloud state from Mock Cloud API."""
    return get(f"/cloud/state?service={service_name}")

def invoke_cloud_action(service_name: str, action: dict) -> dict:
    """Invoke an autonomous optimization action via Mock Cloud API."""
    return post("/cloud/action", {"service": service_name, "action": action})

def reset_mock_cloud(service_name: str = "all", seed_state: dict | None = None) -> dict:
    """Reset the mock cloud environment to seed state."""
    return post("/cloud/reset", {"service": service_name, "seed": seed_state})

def fetch_initial_seed_state(service_name: str = "orders-api") -> dict:
    """Fetch the configured seed initial state from Mock Cloud API."""
    return get(f"/cloud/initial_state?service={service_name}")

def update_initial_seed_state(service_name: str, seed: dict) -> dict:
    """Update configured seed initial state via Mock Cloud API."""
    return post("/cloud/seed", {"service": service_name, "seed": seed})

# -----------------------------------------------------------------------------
# BACKWARDS COMPATIBILITY HELPERS
# -----------------------------------------------------------------------------

def load_state(service: dict) -> dict:
    return post("/load_state", {"service": service})

def execute_action(service_name: str, action: dict) -> dict:
    return invoke_cloud_action(service_name, action)

def get_state(service_name: str) -> dict:
    return fetch_cloud_state(service_name)

def refresh_data(service: dict, latest_traffic: dict | None = None) -> dict:
    return post("/refresh", {"service": service, "latest_traffic": latest_traffic or {}})
