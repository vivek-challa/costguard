from __future__ import annotations
from typing import Any, Dict, List, TypedDict, Optional

class CostGuardState(TypedDict, total=False):
    request: str
    raw_input: Dict[str, Any]
    intent: Dict[str, Any]
    service: Dict[str, Any]
    history: List[Dict[str, Any]]
    freshness: Dict[str, Any]
    diagnosis: Dict[str, Any]
    candidate_actions: List[Dict[str, Any]]
    approved_actions: List[Dict[str, Any]]
    rejected_actions: List[Dict[str, Any]]
    decision: Dict[str, Any]
    execution: Dict[str, Any]
    verification: Dict[str, Any]
    response: str
    trace: List[Dict[str, Any]]
    llm_mode: str
    error: Optional[str]
    fleet_services: Optional[Dict[str, Any]]
    fleet_review: Optional[List[Dict[str, Any]]]
