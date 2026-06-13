"""@FixAuthor — the patch writer in the Rollback Room.

Framework: Codex (OpenAI-compatible).

@FixAuthor turns @RootCause's fix spec into an actual unified diff plus a
regression test, posts it as shared room state, and @mentions @Reviewer to get
adversarially checked by a *different* model. When @Reviewer bounces the patch
back with required changes, @FixAuthor revises and re-posts — the live
author↔reviewer bounce that is this project's signature.

One hard rule lives here too: if the patch touches a high-blast-radius surface
(migrations, auth, money, infra), @FixAuthor cannot ship it on its own — it must
pause at a rule-enforced human gate (@EM) before declaring the patch ready.
"""

from __future__ import annotations

HANDLE = "FixAuthor"
ROLE = "patch author who writes the unified diff + regression test"
HANDS_OFF_TO = ["Reviewer"]

HIGH_RISK_PATHS = ("migrations/", "auth/", "billing/", "payments/", "infra/", "terraform/")
HIGH_RISK_HINTS = ("schema", "migration", "auth", "token", "secret", "charge", "refund", "deploy")
MAX_REVISIONS = 3


def _model_complete(prompt: str) -> str:
    try:
        from models import get_client
    except Exception:
        return _canned_completion(prompt)
    try:
        client = get_client("fixauthor")
    except Exception:
        return _canned_completion(prompt)
    if hasattr(client, "complete"):
        return client.complete(prompt)
    response = client.chat.completions.create(
        model="codex-mini-latest",
        messages=[{"role": "user", "content": prompt}],
    )
    return response.choices[0].message.content


def _canned_completion(prompt: str) -> str:
    if "REVISE" in prompt:
        return (
            "REVISED: added a regression test that double-fires confirm() under "
            "retry and asserts a single charge, plus a rollback note to dpl_8b07."
        )
    return (
        "DRAFTED: restore ttl=PREV_TTL on the write-through set and clamp it to a "
        "non-zero floor so the idempotency guard can never expire instantly."
    )


def _read_spec(message) -> dict:
    payload = message.payload or {}
    spec = payload.get("fix_spec") or {}
    return {
        "incident_id": payload.get("incident", spec.get("incident", "INC-4471")),
        "root_cause": payload.get("root_cause", "unspecified root cause"),
        "target_file": spec.get("file", "src/checkout/idempotency.py"),
        "change": spec.get("change", "restore the explicit ttl on cache.set"),
        "summary": spec.get("guard", "apply the fix described by @RootCause"),
        "tests": spec.get("tests", []),
        "review_feedback": payload.get("review_feedback"),
        "prior_patch": payload.get("patch"),
        "revision": payload.get("revision", 0),
    }


def _build_diff(spec: dict) -> str:
    target = spec["target_file"]
    return (
        f"--- a/{target}\n"
        f"+++ b/{target}\n"
        "@@ -56,7 +56,8 @@ def remember(key, payload):\n"
        "-    cache.set(key, payload)\n"
        "+    ttl = max(PREV_TTL, MIN_IDEMPOTENCY_TTL)\n"
        "+    cache.set(key, payload, ttl=ttl)\n"
    )


def _build_test(spec: dict) -> str:
    return (
        "def test_confirm_is_idempotent_under_retry():\n"
        "    key = idempotency.key_for(order)\n"
        "    confirm(order, key); confirm(order, key)\n"
        "    assert charges_for(order) == 1\n"
        "\n"
        "def test_idempotency_key_outlives_retry_window():\n"
        "    remember(key, payload)\n"
        "    assert cache.ttl(key) >= RETRY_WINDOW_MS\n"
    )


def _is_high_risk(spec: dict, diff: str) -> bool:
    haystack = f"{spec['target_file']} {diff}".lower()
    if any(path in haystack for path in HIGH_RISK_PATHS):
        return True
    return any(hint in haystack for hint in HIGH_RISK_HINTS)


def _author_note(spec: dict, revision: int) -> str:
    if revision == 0:
        prompt = f"DRAFT patch for {spec['incident_id']}: {spec['summary']}"
        return _model_complete(prompt)
    prompt = (
        f"REVISE patch for {spec['incident_id']} given reviewer feedback: "
        f"{spec['review_feedback']}"
    )
    return _model_complete(prompt)


async def handle(room, message) -> None:
    spec = _read_spec(message)
    revision = spec["revision"]

    if spec["review_feedback"] and revision >= MAX_REVISIONS:
        await room.post(
            sender=HANDLE,
            text=(
                f"@Reviewer and I have bounced this {MAX_REVISIONS}x and still "
                f"disagree on {spec['incident_id']}. Kicking the call upstairs."
            ),
            mentions=[],
        )
        return await _escalate(room, spec, _build_diff(spec), reason="reviewer deadlock")

    diff = _build_diff(spec)
    test = _build_test(spec)
    note = _author_note(spec, revision)

    if _is_high_risk(spec, diff):
        return await _escalate(room, spec, diff, reason="high-risk surface")

    verb = "patch" if revision == 0 else f"revision {revision}"
    intro = (
        f"Here's the {verb} for {spec['incident_id']} — root cause: "
        f"{spec['root_cause']}. {note} @Reviewer, tear it apart."
    )
    await room.post(
        sender=HANDLE,
        text=intro,
        mentions=["Reviewer"],
        payload={
            "incident_id": spec["incident_id"],
            "target_file": spec["target_file"],
            "patch": diff,
            "test": test,
            "author_note": note,
            "revision": revision,
            "high_risk": False,
        },
    )


async def _escalate(room, spec, diff, reason: str) -> None:
    prompt = (
        f"{spec['incident_id']} fix for {spec['target_file']} flagged: {reason}. "
        f"This cannot ship without a human EM sign-off. Approve, or send back with "
        f"changes.\n\n{diff}"
    )
    reply = await room.await_human("EM", prompt)
    decision = (reply.payload or {}).get("decision", "").lower()
    approved = decision == "approve" or "approve" in reply.text.lower()

    if approved:
        await room.post(
            sender=HANDLE,
            text=(
                f"@Reviewer — @EM signed off on {spec['incident_id']} despite the "
                f"{reason}. Final adversarial pass, then we ship."
            ),
            mentions=["Reviewer"],
            payload={
                "incident_id": spec["incident_id"],
                "target_file": spec["target_file"],
                "patch": diff,
                "test": _build_test(spec),
                "revision": spec["revision"],
                "high_risk": True,
                "em_approved": True,
            },
        )
        return

    await room.post(
        sender=HANDLE,
        text=(
            f"@EM held {spec['incident_id']}: {reply.text}. Reworking before any "
            f"deploy — no override on this gate."
        ),
        mentions=[],
        payload={
            "incident_id": spec["incident_id"],
            "em_approved": False,
            "em_note": reply.text,
        },
    )


def specialist():
    from band_harness import Specialist

    def adapter_factory():
        from thenvoi.adapters.codex import CodexAdapter

        return CodexAdapter(model="codex-mini-latest")

    return Specialist(
        handle=HANDLE,
        role=ROLE,
        adapter_factory=adapter_factory,
        hands_off_to=HANDS_OFF_TO,
        config_key="fixauthor",
    )
