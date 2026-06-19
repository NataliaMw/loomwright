"""Ouroboros CLI — the one-line entry point judges can run without cloning.

    pipx run ouroboros demo     # the keyless deterministic loop (real subprocess QA)
    pipx run ouroboros try      # run the loop on a BUNDLED buggy repo, keyless, end-to-end
    pipx run ouroboros run --repo ../yours --test "pytest -q" --file src/x.py --goal "..."

`demo` and `try` need no API keys and no network — they execute real Python tests in a
subprocess and show the generate→check→revise loop close. `run` points the loop at YOUR
repo and YOUR test command; add an AI/ML API key to let a model write the fixes.
"""

from __future__ import annotations

import asyncio
import os
import shutil
import subprocess
import sys
import tempfile

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_HERE, "shared"))
sys.path.insert(0, _HERE)


def _bundled_example() -> str:
    # Installed: ships as package data under shared/examples. Dev tree: ./examples.
    for cand in (os.path.join(_HERE, "shared", "examples", "cart_demo"),
                 os.path.join(_HERE, "examples", "cart_demo")):
        if os.path.isdir(cand):
            return cand
    return os.path.join(_HERE, "shared", "examples", "cart_demo")


def cmd_demo() -> int:
    import demo
    saved = sys.argv
    sys.argv = ["demo"]   # demo.main() argparses sys.argv; keep it clean → runs the gallery
    try:
        asyncio.run(demo.main())
    finally:
        sys.argv = saved
    return 0


def cmd_try() -> int:
    """Run the real loop on a bundled buggy repo — keyless, end to end. Copies the
    example to a temp dir so re-runs always start from the bug."""
    src = _bundled_example()
    if not os.path.isdir(src):
        print("bundled example not found; run `ouroboros demo` instead.")
        return 2
    work = tempfile.mkdtemp(prefix="ouroboros_try_")
    dst = os.path.join(work, "cart_demo")
    shutil.copytree(src, dst)
    print(f"Running the loop on a bundled buggy repo (keyless):\n  {dst}\n")
    # stdlib-only test command so `try` needs ZERO extra packages (no pytest).
    test_cmd = f"{sys.executable} tests/test_cart.py"
    # Keyless: if no model key, the loop applies the bundled reference fix so it can
    # close end-to-end — but the gate is still the REAL pytest run. With a key set,
    # a model writes the fix instead.
    fallback = os.path.join(dst, ".fix", "cart.py")
    return _run_repo(dst, test_cmd, "src/cart.py",
                     "discount_pct is a percentage; 10 means 10% off, not 10x",
                     fallback_fix=fallback)


def cmd_run(argv: list[str]) -> int:
    import argparse
    p = argparse.ArgumentParser(prog="ouroboros run")
    p.add_argument("--repo", required=True)
    p.add_argument("--test", required=True)
    p.add_argument("--file")
    p.add_argument("--goal", default="make the failing tests pass")
    p.add_argument("--max-revisions", type=int, default=3)
    a = p.parse_args(argv)
    return _run_repo(os.path.abspath(os.path.expanduser(a.repo)), a.test, a.file,
                     a.goal, a.max_revisions)


def _run_repo(repo: str, test: str, file: str | None, goal: str, max_rev: int = 3,
              fallback_fix: str | None = None) -> int:
    # Delegate to the verified run_on_repo loop by invoking it in-process.
    import run_on_repo
    saved = sys.argv
    sys.argv = ["run_on_repo", "--repo", repo, "--test", test, "--goal", goal,
                "--max-revisions", str(max_rev)] + (["--file", file] if file else []) \
               + (["--fallback-fix", fallback_fix] if fallback_fix else [])
    try:
        return run_on_repo.main()
    finally:
        sys.argv = saved


HELP = """ouroboros — any task, the loop it needs

  ouroboros demo            keyless deterministic loop (real subprocess QA), two tasks
  ouroboros try             run the loop on a bundled buggy repo, keyless, end to end
  ouroboros run  --repo DIR --test "CMD" [--file F] [--goal G]
                            run the loop on YOUR repo + YOUR tests
                            (add AIMLAPI_API_KEY to let a model write the fixes)

  https://github.com/NataliaMw/ouroboros · https://ouroboros-rust.vercel.app/
"""


def main() -> int:
    args = sys.argv[1:]
    if not args or args[0] in ("-h", "--help", "help"):
        print(HELP)
        return 0
    cmd, rest = args[0], args[1:]
    if cmd == "demo":
        return cmd_demo()
    if cmd == "try":
        return cmd_try()
    if cmd == "run":
        return cmd_run(rest)
    print(f"unknown command: {cmd}\n")
    print(HELP)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
