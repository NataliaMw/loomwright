"""@Triage — incident triage for Rollback Room (framework: Pydantic AI).

First responder in the room. Ingests the firing alert plus the suspect deploy
diff, normalizes them into a structured incident brief (severity, blast radius,
suspected surface, the diff hunks worth scrutinizing), then @mentions @RootCause
so the room can start debating cause.

Offline-safe: the model call and the Pydantic AI adapter are imported lazily, so
the LocalRoom demo runs deterministically with zero credentials. When no model
client is available we fall back to a deterministic brief built from fixtures.
"""

from __future__ import annotations

import json

HANDLE = "Triage"
ROLE = "incident triage lead"
HANDS_OFF_TO = ["RootCause"]

MISSION = (
    "Turn a raw production alert and the suspect deploy diff into a crisp, "
    "structured incident brief the rest of the room can act on. You do not guess "
    "root cause — you frame the blast radius and point @RootCause at the diff "
    "hunks that matter."
)


def _alert_fixture() -> dict:
    return {
        "alert_id": "PD-4417",
        "title": "5xx surge on checkout-api",
        "service": "checkout-api",
        "fired_at": "2026-06-13T14:02:11Z",
        "signal": "error_rate",
        "baseline": "0.3%",
        "current": "11.8%",
        "affected_endpoints": ["POST /v2/checkout", "POST /v2/checkout/confirm"],
        "linked_monitor": "checkout-api error budget burn (fast)",
    }


def _deploy_fixture() -> dict:
    return {
        "deploy_id": "dpl_9c1f",
        "service": "checkout-api",
        "shipped_at": "2026-06-13T13:58:40Z",
        "author": "marisol.ferrer",
        "pr": "#2281 — switch idempotency cache to write-through",
        "diff": [
            {
                "file": "src/checkout/idempotency.py",
                "hunk": (
                    "- key = f\"idemp:{order_id}\"\n"
                    "+ key = f\"idemp:{order_id}:{tenant_id}\"\n"
                    "  cache.set(key, payload, ttl=PREV_TTL)\n"
                    "- cache.set(key, payload, ttl=PREV_TTL)\n"
                    "+ cache.set(key, payload)"
                ),
            },
            {
                "file": "src/checkout/handlers.py",
                "hunk": (
                    "- record = store.get(order_id)\n"
                    "+ record = store.get(order_id, tenant_id)\n"
                    "  return confirm(record)"
                ),
            },
        ],
        "rollback_target": "dpl_8b07",
    }


def _read_incident(message) -> dict:
    payload = getattr(message, "payload", None) or {}
    alert = payload.get("alert") or _alert_fixture()
    deploy = payload.get("deploy") or _deploy_fixture()
    return {"alert": alert, "deploy": deploy}


def _severity_for(alert: dict) -> str:
    try:
        current = float(str(alert.get("current", "0")).rstrip("%"))
    except ValueError:
        current = 0.0
    if current >= 10.0:
        return "SEV1"
    if current >= 2.0:
        return "SEV2"
    return "SEV3"


def _suspect_files(deploy: dict) -> list[str]:
    return [hunk["file"] for hunk in deploy.get("diff", [])]


def _canned_summary(incident: dict, severity: str) -> str:
    alert = incident["alert"]
    deploy = incident["deploy"]
    return (
        f"{severity} on {alert['service']}: error rate {alert['baseline']} → "
        f"{alert['current']} since {deploy['shipped_at']}. Prime suspect is "
        f"{deploy['pr']} ({deploy['deploy_id']}) — it reshapes the idempotency "
        f"cache key and drops the explicit TTL. Endpoints bleeding: "
        f"{', '.join(alert['affected_endpoints'])}."
    )


def _model_summary(incident: dict, severity: str) -> str:
    try:
        from models import get_client
    except ImportError:
        return _canned_summary(incident, severity)
    client = get_client(ROLE)
    if client is None:
        return _canned_summary(incident, severity)
    prompt = (
        "You are an incident triage lead. In two tight sentences, summarize this "
        "incident for a room of on-call engineers. State severity, what regressed, "
        "and which deploy is the prime suspect. No preamble.\n\n"
        f"SEVERITY: {severity}\n"
        f"INCIDENT: {json.dumps(incident, indent=2)}"
    )
    try:
        text = client.complete(prompt)
    except Exception:
        return _canned_summary(incident, severity)
    text = (text or "").strip()
    return text or _canned_summary(incident, severity)


def _build_brief(incident: dict) -> dict:
    alert = incident["alert"]
    deploy = incident["deploy"]
    severity = _severity_for(alert)
    return {
        "severity": severity,
        "service": alert["service"],
        "alert_id": alert["alert_id"],
        "summary": _model_summary(incident, severity),
        "blast_radius": alert["affected_endpoints"],
        "metric_jump": {"baseline": alert["baseline"], "current": alert["current"]},
        "suspect_deploy": {
            "deploy_id": deploy["deploy_id"],
            "pr": deploy["pr"],
            "author": deploy["author"],
            "shipped_at": deploy["shipped_at"],
            "rollback_target": deploy["rollback_target"],
        },
        "diff_hunks_to_inspect": _suspect_files(deploy),
        "diff": deploy["diff"],
    }


def _brief_text(brief: dict) -> str:
    files = ", ".join(brief["diff_hunks_to_inspect"])
    return (
        f"[{brief['severity']}] {brief['summary']}\n"
        f"@RootCause — own the cause. Scrutinize these hunks first: {files}. "
        f"Rollback target on standby is {brief['suspect_deploy']['rollback_target']}."
    )


async def handle(room, message) -> None:
    incident = _read_incident(message)
    brief = _build_brief(incident)
    await room.post(
        sender=HANDLE,
        text=_brief_text(brief),
        mentions=["RootCause"],
        payload={"incident_brief": brief},
    )


def _adapter_factory():
    from pydantic_ai import Agent as PydanticAgent
    from thenvoi.adapters.pydantic_ai import PydanticAIAdapter

    agent = PydanticAgent("openai:gpt-4o", system_prompt=MISSION)
    return PydanticAIAdapter(agent)


def specialist():
    from band_harness import Specialist

    return Specialist(
        handle=HANDLE,
        role=ROLE,
        adapter_factory=lambda: _adapter_factory(),
        hands_off_to=HANDS_OFF_TO,
        config_key="triage",
    )
