"""Auto-trader alerts: persist runtime issues to a JSONL log so the morning
briefing can surface them. Best-effort macOS notification as a fallback."""

import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path

ALERTS_FILE = Path.home() / "Dropbox/claude-scratch/scratch/trader-alerts.jsonl"

VALID_SEVERITIES = {"critical", "warning", "info"}
VALID_TYPES = {"cron_failure", "trade_error", "stuck_order", "audit_mismatch"}
SCAN_TYPES = {"stuck_order", "audit_mismatch"}  # latest scan supersedes prior


def _atomic_write_text(path, content):
    """Atomic file replace: write sibling tempfile, fsync, then os.replace.
    POSIX-atomic so a concurrent append to the original file can't interleave
    with the rewrite."""
    tmp = path.with_name(path.name + ".tmp")
    with tmp.open("w") as f:
        f.write(content)
        f.flush()
        os.fsync(f.fileno())
    os.replace(str(tmp), str(path))


def _mark_prior_resolved(alert_type, reason):
    """Mark all prior unresolved alerts of this type as resolved with the given reason."""
    if not ALERTS_FILE.exists():
        return 0
    lines_out = []
    count = 0
    for line in ALERTS_FILE.read_text().splitlines():
        if not line.strip():
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            lines_out.append(line)
            continue
        if entry.get("type") == alert_type and not entry.get("resolved"):
            entry["resolved"] = True
            entry["resolved_by"] = reason
            count += 1
        lines_out.append(json.dumps(entry))
    if count:
        _atomic_write_text(ALERTS_FILE, "\n".join(lines_out) + "\n")
    return count


def _resolve_prior(alert_type):
    """Supersede prior unresolved alerts when a new alert of this type fires."""
    _mark_prior_resolved(alert_type, reason="superseded")


def resolve_scan(alert_type, reason="clean_scan"):
    """Mark prior unresolved scan alerts as resolved when a scan comes back clean.
    Without this, stale audit/stuck-order warnings linger forever because the
    supersede-on-new-alert path only triggers when the next scan also fails."""
    if alert_type not in SCAN_TYPES:
        return 0
    return _mark_prior_resolved(alert_type, reason=reason)


def log_alert(severity, alert_type, message, details=None):
    """Append an alert to the persistent log and fire a macOS notification."""
    if severity not in VALID_SEVERITIES:
        severity = "warning"
    if alert_type not in VALID_TYPES:
        alert_type = "trade_error"

    if alert_type in SCAN_TYPES:
        _resolve_prior(alert_type)

    entry = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "severity": severity,
        "type": alert_type,
        "message": message,
        "details": details or {},
        "resolved": False,
    }

    ALERTS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with ALERTS_FILE.open("a") as f:
        f.write(json.dumps(entry) + "\n")

    try:
        title = f"Auto-Trader {severity.upper()}"
        safe_msg = message.replace('"', "'")[:200]
        subprocess.run(
            ["osascript", "-e", f'display notification "{safe_msg}" with title "{title}"'],
            capture_output=True,
            timeout=5,
        )
    except Exception:
        pass


def check_stuck_orders(orders, hours_threshold=24):
    """Return open DAY orders older than hours_threshold."""
    now = datetime.now(timezone.utc)
    stuck = []
    for o in orders:
        status = str(o.get("status", "")).lower()
        if status not in ("new", "accepted", "pending_new", "partially_filled"):
            continue
        submitted = o.get("submitted_at")
        if isinstance(submitted, str):
            try:
                submitted = datetime.fromisoformat(submitted.replace("Z", "+00:00"))
            except ValueError:
                continue
        if not submitted:
            continue
        if submitted.tzinfo is None:
            submitted = submitted.replace(tzinfo=timezone.utc)
        age_hours = (now - submitted).total_seconds() / 3600
        if age_hours >= hours_threshold:
            stuck.append({
                "symbol": o.get("symbol"),
                "side": o.get("side"),
                "qty": o.get("qty"),
                "notional": o.get("notional"),
                "age_hours": round(age_hours, 1),
                "order_id": o.get("id"),
            })
    return stuck


def alert_stuck_orders(orders, hours_threshold=24):
    """Convenience wrapper: detect stuck orders and log a single warning.
    Clean scans clear prior unresolved stuck-order warnings."""
    stuck = check_stuck_orders(orders, hours_threshold)
    if not stuck:
        resolve_scan("stuck_order")
        return []
    summary_parts = [f"{s['side']} {s['symbol']} ({s['age_hours']}h)" for s in stuck]
    log_alert(
        "warning",
        "stuck_order",
        f"{len(stuck)} order(s) open >{hours_threshold}h: {', '.join(summary_parts)}",
        details={"orders": stuck, "threshold_hours": hours_threshold},
    )
    return stuck


def alert_audit_mismatch(missing, mismatches, threshold=1):
    """Log a warning if audit found unreconciled trades above threshold.
    Clean scans clear prior unresolved audit_mismatch warnings."""
    if len(missing) < threshold and len(mismatches) < threshold:
        resolve_scan("audit_mismatch")
        return False
    log_alert(
        "warning",
        "audit_mismatch",
        f"Trade Log out of sync: {len(missing)} missing, {len(mismatches)} amount mismatches. Run --audit --fix.",
        details={"missing_count": len(missing), "mismatch_count": len(mismatches)},
    )
    return True


