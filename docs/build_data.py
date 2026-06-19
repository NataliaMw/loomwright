"""Render the real demo run into web/data.json for the static viewer.

This does NOT mock anything: it drives the same Band room the CLI demo uses and
captures the actual transcript + the loops the room built. The web page is just a
faithful replay of a real run, so what judges see in the browser is what the code
actually does.

Run from the repo root:  python web/build_data.py
"""

from __future__ import annotations

import asyncio
import json
import os
import sys

_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_root, "shared"))
sys.path.insert(0, _root)

from band_harness import LocalRoom
from tasks import REGISTRY

import demo  # reuse the exact room wiring + recruitable critics


def _spec_to_dict(spec) -> dict:
    return {
        "task": {"title": spec.task.title, "kind": spec.task.kind,
                 "touches": spec.task.touches},
        "checks": [{"name": c.name, "why": c.why, "required": c.required}
                   for c in spec.checks],
        "critics": [{"handle": c.handle, "lens": c.lens,
                     "recruited_on_demand": c.recruited_on_demand}
                    for c in spec.critics],
        "max_revisions": spec.max_revisions,
        "exit_condition": spec.exit_condition,
        "human_gate": spec.human_gate,
        "rationale": spec.rationale,
        "fingerprint": spec.fingerprint(),
    }


async def _capture(entry: dict) -> dict:
    task = entry["task"]
    room = demo._build_room()
    await demo._drive(room, entry)
    spec = None
    record = None
    transcript = []
    qa_runs = []
    for msg in room.transcript:
        transcript.append({
            "sender": msg.sender,
            "mentions": msg.mentions,
            "text": msg.text,
            "qa": (msg.payload or {}).get("qa_results"),
        })
        if (msg.payload or {}).get("loop_spec") is not None:
            spec = msg.payload["loop_spec"]
        if (msg.payload or {}).get("loop_record") is not None:
            record = msg.payload["loop_record"]
        if (msg.payload or {}).get("qa_results") is not None:
            qa_runs.append((msg.payload or {})["qa_results"])
    return {
        "task": {"title": task.title, "description": task.description,
                 "kind": task.kind, "touches": task.touches,
                 "high_stakes": task.high_stakes},
        "loop": _spec_to_dict(spec),
        "record": record,
        "transcript": transcript,
        "recruited": room.recruited,
        "qa_runs": qa_runs,
        "code": {"buggy": entry["buggy"], "fixed": entry["fixed"], "tests": entry["tests"]},
    }


async def main() -> None:
    a = await _capture(REGISTRY["a"])
    b = await _capture(REGISTRY["b"])
    data = {
        "tagline": "the room that engineers the loop, then runs it",
        "tasks": [a, b],
        "different": a["loop"]["fingerprint"] != b["loop"]["fingerprint"],
    }
    here = os.path.dirname(os.path.abspath(__file__))
    out = os.path.join(here, "data.json")
    with open(out, "w") as f:
        json.dump(data, f, indent=2)
    print(f"wrote {out}  (loops differ: {data['different']})")

    # Inject the real run into a self-contained index.html so the page works on
    # GitHub Pages AND when double-clicked locally (no fetch, no server needed).
    template_path = os.path.join(here, "index.template.html")
    with open(template_path) as f:
        template = f.read()
    embedded = json.dumps(data).replace("</", "<\\/")  # keep the </script> safe
    html = template.replace("__DATA__", embedded)
    index_path = os.path.join(here, "index.html")
    with open(index_path, "w") as f:
        f.write(html)
    print(f"wrote {index_path}  (self-contained, {len(html)} bytes)")


if __name__ == "__main__":
    asyncio.run(main())
