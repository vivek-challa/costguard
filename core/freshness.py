from datetime import datetime, timezone
import os

def parse_ts(value: str):
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except ValueError:
        return None

def freshness_check(service: dict, raw_input: dict) -> dict:
    threshold = int(os.getenv("FRESHNESS_THRESHOLD_MINUTES", "30"))
    now = parse_ts(raw_input.get("current_time")) or datetime.now(timezone.utc)
    metric_ts = parse_ts(service.get("timestamp"))
    latest = raw_input.get("latest_traffic") or {}
    latest_ts = parse_ts(latest.get("timestamp"))

    reasons = []
    age_minutes = None
    stale = False
    contradicted = False

    if metric_ts:
        age_minutes = max(0, (now - metric_ts).total_seconds() / 60)
        stale = age_minutes > threshold
    else:
        stale = True
        reasons.append("missing service timestamp")

    if latest_ts and metric_ts and latest_ts > metric_ts:
        old_rpm = service.get("requests_per_minute", 0)
        new_rpm = latest.get("requests_per_minute", old_rpm)
        if old_rpm == 0 and new_rpm > 100:
            contradicted = True
        elif old_rpm > 0 and new_rpm >= old_rpm * 2.0:
            contradicted = True
        if contradicted:
            reasons.append("newer traffic data materially contradicts cached load")

    if stale:
        reasons.append(f"observation age {age_minutes:.1f} min exceeds {threshold} min" if age_minutes is not None else "observation is stale")

    return {
        "stale": stale or contradicted,
        "age_minutes": round(age_minutes, 1) if age_minutes is not None else None,
        "contradicted": contradicted,
        "latest_traffic_timestamp": latest.get("timestamp"),
        "reasons": reasons,
    }
