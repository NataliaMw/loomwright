"""Canned scenario + canned model outputs for the Rollback Room demo.

Two jobs:
  1. KICKOFF_* — the believable production incident (firing alert + suspect
     deploy diff) and the structured fix spec that drive the deterministic
     LocalRoom run.
  2. canned_model_output() — the reply each role's offline model returns, so the
     transcript is reproducible frame-for-frame on the demo video.

The scenario is a payments regression on purpose: it routes the patch onto a
high-risk surface (billing/idempotency), which is what trips the rule-enforced
human EM gate later in the room.
"""

from __future__ import annotations


KICKOFF_ALERT = {
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

KICKOFF_DEPLOY = {
    "deploy_id": "dpl_9c1f",
    "service": "checkout-api",
    "shipped_at": "2026-06-13T13:58:40Z",
    "author": "marisol.ferrer",
    "pr": "#2281 — switch idempotency cache to write-through",
    "diff": [
        {
            "file": "src/billing/idempotency.py",
            "hunk": (
                "- key = f\"idemp:{order_id}\"\n"
                "+ key = f\"idemp:{order_id}:{tenant_id}\"\n"
                "  cache.set(key, payload, ttl=PREV_TTL)\n"
                "- cache.set(key, payload, ttl=PREV_TTL)\n"
                "+ cache.set(key, payload)"
            ),
        },
        {
            "file": "src/billing/handlers.py",
            "hunk": (
                "- record = store.get(order_id)\n"
                "+ record = store.get(order_id, tenant_id)\n"
                "  return confirm(record)"
            ),
        },
    ],
    "rollback_target": "dpl_8b07",
}

KICKOFF_FIX_SPEC = {
    "incident_id": "INC-4471",
    "root_cause": (
        "write-through idempotency cache lost its explicit TTL, so duplicate "
        "charge guards expire immediately and confirm() double-bills under retry"
    ),
    "target_file": "src/billing/idempotency.py",
    "summary": "restore the explicit idempotency TTL and null-guard the tenant key",
    "touched_surfaces": ["billing", "payments"],
}

AUTHOR_TARGET_FILE = "src/checkout/idempotency_ttl.py"
AUTHOR_ROOT_CAUSE = (
    "write-through cache lost its explicit TTL, so the dedupe guard expires "
    "instantly and confirm() reprocesses orders under client retry"
)
AUTHOR_SUMMARY = "restore the explicit idempotency TTL and clamp it to a non-zero floor"

KICKOFF_TEXT = (
    "Prod is on fire. PagerDuty PD-4417: 5xx surge on checkout-api right after "
    "deploy dpl_9c1f. @Triage — frame it and kick off the room."
)

EM_APPROVAL_LINE = (
    "APPROVE. I own the risk on billing for INC-4471 — the TTL restore is the "
    "smallest safe change and we're actively double-charging. Ship it behind the "
    "checkout-idempotency flag and page me if burn rate doesn't drop in 10m. — Dana, EM"
)


_CANNED = {
    "triage": (
        "SEV1 on checkout-api: error rate jumped 0.3% -> 11.8% since deploy "
        "dpl_9c1f (PR #2281, write-through idempotency). POST /v2/checkout and "
        "/v2/checkout/confirm are bleeding 5xx — prime suspect is the dropped "
        "cache TTL in src/billing/idempotency.py."
    ),
    "rootcause": (
        "ROOT CAUSE: src/billing/idempotency.py lost its explicit ttl=PREV_TTL on "
        "cache.set, so the idempotency record expires on the next read and confirm() "
        "re-processes the charge under client retry. | EVIDENCE: "
        "src/billing/idempotency.py:* | FIX: restore the explicit TTL and keep the "
        "tenant-scoped key null-safe so retries hit a live idempotency record."
    ),
    "fixauthor": (
        "DRAFTED: restore ttl=PREV_TTL on the write-through set and clamp it to a "
        "non-zero floor so the idempotency guard can never expire instantly."
    ),
    "fixauthor_revise": (
        "REVISED: added a regression test that double-fires confirm() under retry "
        "and asserts a single charge, plus a one-line rollback note pointing at "
        "dpl_8b07."
    ),
    "reviewer_first": (
        "- No regression test reproduces the double-charge under client retry.\n"
        "- Missing rollback plan if the TTL restore still mis-keys tenants.\n"
        "- ttl=PREV_TTL could itself be misconfigured to 0 — clamp it."
    ),
    "reviewer_clean": "",
}


def canned_model_output(role: str, prompt: str) -> str:
    key = (role or "").strip().lower()
    if key == "fixauthor" and "REVISE" in prompt:
        return _CANNED["fixauthor_revise"]
    if key == "reviewer":
        if "(first pass)" in prompt:
            return _CANNED["reviewer_first"]
        return _CANNED["reviewer_clean"]
    return _CANNED.get(key, "ACK.")
