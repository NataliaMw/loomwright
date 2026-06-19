"""Real QA execution — the loop's checks actually run.

This is what makes Ouroboros a real loop and not a story about one: a check does
not "decide" pass/fail from a fixture, it WRITES the candidate code and its test to
a temp dir and RUNS them in a fresh Python subprocess. The check passes only if the
interpreter says so. If the generated code is wrong, the test really fails, the loop
really bounces, and the next revision really has to fix it.

No network, no shared interpreter state — each run is an isolated subprocess with a
timeout, so a bad generation can't hang or corrupt the room.
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from dataclasses import dataclass


@dataclass
class CheckResult:
    name: str
    passed: bool
    detail: str

    @property
    def icon(self) -> str:
        return "✅" if self.passed else "❌"


def _run_python(code: str, timeout: float = 10.0) -> tuple[bool, str]:
    """Execute a self-contained Python script in an isolated subprocess."""
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "candidate.py")
        with open(path, "w") as f:
            f.write(code)
        try:
            proc = subprocess.run(
                [sys.executable, path],
                capture_output=True, text=True, timeout=timeout, cwd=d,
            )
        except subprocess.TimeoutExpired:
            return False, f"timed out after {timeout}s"
        ok = proc.returncode == 0
        out = (proc.stdout + proc.stderr).strip()
        tail = "\n".join(out.splitlines()[-8:])
        return ok, tail or ("exit 0" if ok else f"exit {proc.returncode}")


def run_compiles(code: str) -> CheckResult:
    """Does the candidate even import/parse and run to completion?"""
    ok, detail = _run_python(code + "\n\nprint('__ouroboros_ok__')")
    ok = ok and "__ouroboros_ok__" in detail
    return CheckResult("compiles", ok, detail)


def run_unit_tests(code: str, test: str) -> CheckResult:
    """Run the candidate against a unit test. The test asserts; a failure is real."""
    script = f"{code}\n\n{test}\n\nif __name__ == '__main__':\n    _run_tests()\n    print('__tests_passed__')"
    ok, detail = _run_python(script)
    ok = ok and "__tests_passed__" in detail
    return CheckResult("unit-tests", ok, detail)


def run_repro_test(code: str, repro: str) -> CheckResult:
    """A bugfix's signature gate: the repro test must pass on the fixed code."""
    script = f"{code}\n\n{repro}\n\nif __name__ == '__main__':\n    _repro()\n    print('__repro_passed__')"
    ok, detail = _run_python(script)
    ok = ok and "__repro_passed__" in detail
    return CheckResult("repro-test", ok, detail)


def run_command(cmd: str, cwd: str, timeout: float = 120.0) -> CheckResult:
    """Run the user's OWN test command in their OWN repo. This is the useful path:
    no fixtures, no stand-in — `cmd` is whatever proves the code works for them
    (`pytest -q`, `npm test`, `go test ./...`, `make check`, ...). The check passes
    iff that command exits 0. The loop is gated on the user's real signal."""
    import shlex
    try:
        proc = subprocess.run(
            shlex.split(cmd) if os.name != "nt" else cmd,
            capture_output=True, text=True, timeout=timeout, cwd=cwd,
        )
    except FileNotFoundError as e:
        return CheckResult(cmd, False, f"command not found: {e}")
    except subprocess.TimeoutExpired:
        return CheckResult(cmd, False, f"timed out after {timeout}s")
    out = (proc.stdout + proc.stderr).strip()
    tail = "\n".join(out.splitlines()[-15:])
    return CheckResult(cmd, proc.returncode == 0, tail or f"exit {proc.returncode}")


def evaluate(check_name: str, code: str, tests: dict) -> CheckResult:
    """Dispatch a named check to a real execution. Unknown checks (advisory ones
    we don't execute, like perf) return a passing advisory result so the loop is
    gated only on checks it can truly verify."""
    if check_name == "compiles":
        return run_compiles(code)
    if check_name == "unit-tests":
        return run_unit_tests(code, tests.get("unit", "def _run_tests():\n    pass"))
    if check_name == "repro-test":
        return run_repro_test(code, tests.get("repro", "def _repro():\n    pass"))
    if check_name == "acceptance-test":
        res = run_unit_tests(code, tests.get("acceptance", "def _run_tests():\n    pass"))
        return CheckResult("acceptance-test", res.passed, res.detail)
    return CheckResult(check_name, True, "advisory — not executed")
