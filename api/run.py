"""Hosted live-run endpoint — judges click 'Run live ▶' and a REAL loop executes
server-side, no install, no keys on their side.

Security: this NEVER runs arbitrary judge-supplied code. It runs the loop on a
fixed, bundled buggy example (a small pure function + its test), copied to a temp
dir per request. The model keys live in Vercel env vars and are never returned.

The loop is the real thing: it runs the example's real test in a subprocess; if a
model key is present it asks the AI/ML API to write the fix, otherwise it applies
the bundled reference fix — either way the gate is the real test run.
"""

from http.server import BaseHTTPRequestHandler
import json
import os
import shutil
import subprocess
import sys
import tempfile


# The bundled buggy example, inlined so the function is self-contained on Vercel.
BUGGY = '''def total(items, discount_pct):
    subtotal = sum(p for _, p in items)
    return subtotal - discount_pct * subtotal          # bug: treats 10 as 10x, not 10%
'''

REFERENCE_FIX = '''def total(items, discount_pct):
    subtotal = sum(p for _, p in items)
    return subtotal - (discount_pct / 100) * subtotal   # discount_pct is a percentage
'''

TEST = '''import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from cart import total

def _check():
    assert total([("a", 10.0), ("b", 5.0)], 0) == 15.0
    got = total([("x", 100.0)], 10)
    assert got == 90.0, f"10% off 100 should be 90, got {got}"

if __name__ == "__main__":
    _check()
    print("ok - 2 passed")
'''

AIMLAPI_BASE = "https://api.aimlapi.com/v1"


def _run_test(repo: str) -> tuple[bool, str]:
    try:
        p = subprocess.run([sys.executable, "tests/test_cart.py"],
                           capture_output=True, text=True, timeout=20, cwd=repo)
    except subprocess.TimeoutExpired:
        return False, "timed out"
    out = (p.stdout + p.stderr).strip()
    return p.returncode == 0, "\n".join(out.splitlines()[-8:])


def _model_fix(buggy: str, failure: str) -> str | None:
    key = os.getenv("AIMLAPI_API_KEY")
    if not key:
        return None
    try:
        from openai import OpenAI
        client = OpenAI(base_url=AIMLAPI_BASE, api_key=key)
        r = client.chat.completions.create(
            model=os.getenv("OUROBOROS_AIMLAPI_MODEL", "gpt-4o-mini"),
            temperature=0,
            messages=[{"role": "user", "content":
                "Fix this Python so the failing test passes. Return ONLY the corrected "
                "file, no prose, no fences.\n\nFile:\n" + buggy +
                "\n\nFailing test output:\n" + failure}],
        )
        out = (r.choices[0].message.content or "").strip()
        if out.startswith("```"):
            out = out.strip("`")
            out = out[out.find("\n") + 1:] if "\n" in out else out
        return out or None
    except Exception:
        return None


def run_loop() -> dict:
    work = tempfile.mkdtemp(prefix="ouro_")
    repo = os.path.join(work, "cart_demo")
    os.makedirs(os.path.join(repo, "src"))
    os.makedirs(os.path.join(repo, "tests"))
    open(os.path.join(repo, "src", "cart.py"), "w").write(BUGGY)
    open(os.path.join(repo, "tests", "test_cart.py"), "w").write(TEST)

    events = []
    events.append(("architect", "bugfix loop — exit gate is the repo's real test, max 2 revisions."))
    used_model = False
    status = "needs-human"
    revisions = 0
    try:
        for rev in range(3):
            ok, detail = _run_test(repo)
            revisions = rev
            events.append(("qa", f"revision {rev}: ran the real test → {'PASS ✅' if ok else 'FAIL ❌'}"))
            if ok:
                status = "shipped"
                events.append(("reviewer", "ran the real suite, it's green. Shipping."))
                break
            events.append(("reviewer", "still failing:\n" + detail))
            if rev == 2:
                break
            src = open(os.path.join(repo, "src", "cart.py")).read()
            fixed = _model_fix(src, detail)
            if fixed:
                used_model = True
                events.append(("author", "patching src/cart.py via AI/ML API against the real failure…"))
            else:
                fixed = REFERENCE_FIX
                events.append(("author", "patching src/cart.py (deterministic reference fix)…"))
            open(os.path.join(repo, "src", "cart.py"), "w").write(fixed)
        final_code = open(os.path.join(repo, "src", "cart.py")).read()
    finally:
        shutil.rmtree(work, ignore_errors=True)

    return {"events": events, "status": status, "revisions": revisions,
            "used_model": used_model, "final_code": final_code, "buggy": BUGGY}


class handler(BaseHTTPRequestHandler):
    def _send(self, code, body):
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()
        self.wfile.write(json.dumps(body).encode())

    def do_OPTIONS(self):
        self._send(204, {})

    def do_GET(self):
        # allow a simple GET to trigger too (easier to demo)
        try:
            self._send(200, run_loop())
        except Exception as e:
            self._send(500, {"error": str(e)})

    def do_POST(self):
        try:
            self._send(200, run_loop())
        except Exception as e:
            self._send(500, {"error": str(e)})
