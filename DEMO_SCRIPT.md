# CostGuard — 3–4 Minute Judge Demo Script

## Opening (20 seconds)
“Cloud cost optimization is not just about reducing instances. A cost-saving action can break latency or reliability. CostGuard separates AI reasoning from deterministic safety enforcement. The AI investigates and chooses; code decides what is actually allowed.”

## Test A — Cost optimization
Load `test_a_cost_optimization.json`.
Say:
“Reports-worker has four instances, 0 requests per minute and low CPU. The important part is that CostGuard does not trust one zero reading; it checks recent history.”
Run.
Show:
- Diagnostic candidate: scale_down 4 → 1
- Safety: approved because history confirms near-zero traffic
- Execution
- Verification
- Hourly saving

## Test B — Rising traffic
Load `test_b_rising_traffic.json`.
Say:
“Now I deliberately give the agent a cost-versus-SLA conflict. Traffic doubled from 2100 to 4200 rpm and latency is 260 ms against a 300 ms ceiling.”
Run.
Say:
“Notice the agent increases capacity. This is the point: CostGuard does not blindly minimize cost. Reliability constraints win.”
Show before/after latency and instances.

## Test C — Stale data
Load `test_c_stale_observation.json`.
Say:
“Here the cached metrics are from 08:00, but the latest traffic snapshot is 10:30 and jumps to 5200 rpm. The system treats stale/conflicting data as a safety risk.”
Run.
Show Freshness Checker and conservative branch.

## Test D — Failure recovery
Load `test_d_failed_action.json`.
Say:
“This service is already violating the 300 ms target, but the first scale-up receives capacity_unavailable from the mock cloud API.”
Run.
Show:
- first failure
- recovery_attempted=true
- smaller safe retry
- verification
Say:
“The agent never reports success because a model said so; it checks the actual service state.”

## Closing (15 seconds)
“Every request leaves an auditable trace: what was investigated, what was proposed, what safety rules allowed, what was executed, and what actually changed. That is the agentic loop: investigate, decide, act safely, verify, explain.”
