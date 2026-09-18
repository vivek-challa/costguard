import json
import urllib.request
import urllib.error
import os
from dotenv import load_dotenv

load_dotenv()

def api_url():
    return os.getenv("CLOUD_API_URL", "http://127.0.0.1:8000").rstrip("/")

def post(path: str, payload: dict) -> dict:
    req = urllib.request.Request(api_url()+path, data=json.dumps(payload).encode(),
                                 headers={"Content-Type":"application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read().decode())

def get(path: str) -> dict:
    req = urllib.request.Request(api_url()+path, method="GET")
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read().decode())

def load_state(service: dict) -> dict:
    return post("/load_state", {"service":service})

def execute_action(service_name: str, action: dict) -> dict:
    return post("/execute", {"service_name":service_name, "action":action})

def get_state(service_name: str) -> dict:
    return get("/state/"+service_name)

def refresh_data(service: dict, latest_traffic: dict | None = None) -> dict:
    return post("/refresh", {"service":service, "latest_traffic":latest_traffic or {}})
