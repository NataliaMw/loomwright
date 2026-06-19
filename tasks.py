"""Concrete tasks with REAL code the QA loop executes.

Each task ships a real failing first attempt and a real correct revision, plus real
tests. The loop runs revision 0 (which genuinely fails its signature test), bounces,
then runs the fixed revision (which genuinely passes). When a live model is wired in,
it replaces these attempts — but the tests, and the pass/fail, are always real.
"""

from __future__ import annotations

from loopspec import Task


# --- Task A: a real off-by-one bug in pagination --------------------------- #

TASK_A = Task(
    title="Fix off-by-one in pagination offset",
    description="last page drops one row; pure function, no side effects",
    touches=["pagination"],
    kind="bugfix",
)

A_BUGGY = '''\
def page(items, page_num, size):
    start = page_num * size
    end = start + size - 1          # bug: drops the last row of every page
    return items[start:end]
'''

A_FIXED = '''\
def page(items, page_num, size):
    start = page_num * size
    end = start + size              # fixed: slice end is exclusive
    return items[start:end]
'''

A_TESTS = {
    "unit": '''\
def _run_tests():
    data = list(range(10))
    assert page(data, 0, 3) == [0, 1, 2]
    assert page(data, 1, 3) == [3, 4, 5]
''',
    "repro": '''\
def _repro():
    # the exact bug: a full page must return `size` rows, not size-1
    assert len(page(list(range(10)), 0, 3)) == 3, "page returned a short page"
''',
}


# --- Task B: a real feature (token refresh) on a high-stakes surface -------- #

TASK_B = Task(
    title="Add SSO token refresh to the login flow",
    description="rotate refresh tokens; touches auth and sessions",
    touches=["auth", "sessions"],
    kind="feature",
)

B_BUGGY = '''\
def refresh(session, now):
    # bug: reuses the same refresh token instead of rotating it
    if now >= session["expires_at"]:
        session["access_token"] = "access-" + str(now)
    return session
'''

B_FIXED = '''\
def refresh(session, now):
    if now >= session["expires_at"]:
        session["access_token"] = "access-" + str(now)
        session["refresh_token"] = "refresh-" + str(now)   # rotate on every refresh
        session["expires_at"] = now + 3600
    return session
'''

B_TESTS = {
    "unit": '''\
def _run_tests():
    s = {"access_token": "a0", "refresh_token": "r0", "expires_at": 0}
    out = refresh(dict(s), now=10)
    assert out["access_token"] != "a0"
''',
    "acceptance": '''\
def _run_tests():
    s = {"access_token": "a0", "refresh_token": "r0", "expires_at": 0}
    out = refresh(dict(s), now=10)
    assert out["refresh_token"] != "r0", "refresh token was not rotated"
    assert out["expires_at"] > 10, "expiry was not extended"
''',
}


REGISTRY = {
    "a": {"task": TASK_A, "buggy": A_BUGGY, "fixed": A_FIXED, "tests": A_TESTS},
    "b": {"task": TASK_B, "buggy": B_BUGGY, "fixed": B_FIXED, "tests": B_TESTS},
}
