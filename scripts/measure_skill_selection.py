#!/usr/bin/env python3
"""Measure which skills the agent reads, against the selection query set.

Answer quality and skill selection fail independently, so they are measured
separately. This drives the running local server rather than the agent
in-process, because a skill read is only observable in the tool calls.

    uv run start-server --port 8099        # in another shell
    uv run measure-skill-selection --port 8099

Reports per-skill triggering accuracy. The spec requires re-running this
across the whole menu whenever a skill is added or a description widened --
a broadened description steals triggers from its neighbours, and that shows
up as a fall in *their* accuracy, not its own.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import sys
import time
import urllib.error
import urllib.request
from collections import defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from agent_evaluation.scorers import skill_selection  # noqa: E402
from agent_evaluation.skill_selection import ITEMS, MENU  # noqa: E402

SKILLS_PREFIX = "/skills/"


def ask(base_url: str, question: str, timeout: int, retries: int = 3) -> dict:
    """One question to the agent, returning the skill paths it read.

    A failed request is reported as an error and **never** as a result. A
    request that dies returns zero skill reads, which is indistinguishable
    from the agent correctly reading nothing -- so scoring it would turn an
    outage into a pass on every `avoid` item and a failure on every
    `trigger` one. Errored items are excluded from accuracy instead.

    Retries exist because the upstream SQL server returns 429 under
    concurrency; the backoff is what makes a modest concurrency usable.
    """
    payload = json.dumps({"input": [{"role": "user", "content": question}]}).encode()
    last = ""
    for attempt in range(retries + 1):
        req = urllib.request.Request(
            f"{base_url}/invocations",
            data=payload,
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                data = json.loads(resp.read())
            break
        except Exception as exc:
            last = str(exc)
            if attempt < retries:
                time.sleep(5 * (attempt + 1))
    else:
        return {"skill_reads": [], "error": last}

    reads: list[str] = []
    for entry in data.get("output") or []:
        if entry.get("type") != "function_call":
            continue
        try:
            args = json.loads(entry.get("arguments") or "{}")
        except json.JSONDecodeError:
            continue
        for key in ("file_path", "path", "pattern"):
            value = args.get(key)
            if isinstance(value, str) and value.startswith(SKILLS_PREFIX):
                reads.append(value)
    return {"skill_reads": reads}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--port", type=int, default=8099)
    ap.add_argument("--host", default="localhost")
    ap.add_argument("--concurrency", type=int, default=2,
                    help="the upstream SQL server returns 429 above ~2")
    ap.add_argument("--retries", type=int, default=3)
    ap.add_argument("--timeout", type=int, default=300)
    ap.add_argument("--limit", type=int, help="run only the first N items")
    ap.add_argument("--json-out", type=Path, help="write raw results here")
    args = ap.parse_args()

    base_url = f"http://{args.host}:{args.port}"
    items = ITEMS[: args.limit] if args.limit else ITEMS
    print(f"{len(items)} selection item(s) against {base_url}, {len(MENU)} skills in the menu\n")

    def run(item):
        output = ask(base_url, item.question, args.timeout, args.retries)
        if output.get("error"):
            return item, output, None
        evaluation = skill_selection(
            input={"question": item.question},
            output=output,
            expected_output={
                "expected_skills": sorted(item.expected),
                "tolerated_skills": sorted(item.tolerated),
            },
        )
        return item, output, evaluation

    results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.concurrency) as pool:
        for item, output, evaluation in pool.map(run, items):
            results.append((item, output, evaluation))
            if evaluation is None:
                print(f"  ERR  {item.id:32s} excluded — {output['error'][:70]}")
            else:
                mark = {1.0: "ok  ", 0.5: "warn", 0.0: "FAIL"}[evaluation.value]
                print(f"  {mark} {item.id:32s} {evaluation.comment}")

    errored = [i for i, _, e in results if e is None]
    scored = [(i, e) for i, _, e in results if e is not None]
    by_subject: dict[str, list[float]] = defaultdict(list)
    by_kind: dict[str, list[float]] = defaultdict(list)
    for item, evaluation in scored:
        by_subject[item.subject].append(evaluation.value)
        by_kind[item.kind].append(evaluation.value)

    print("\n── triggering accuracy per skill ──")
    for name in MENU:
        scores = by_subject.get(name) or []
        if scores:
            print(f"  {name:34s} {sum(scores) / len(scores) * 100:5.0f}%  ({len(scores)} items)")
    for name, scores in sorted(by_subject.items()):
        if name not in MENU:
            print(f"  {name:34s} {sum(scores) / len(scores) * 100:5.0f}%  ({len(scores)} items)")

    print("\n── by item kind ──")
    for kind in ("trigger", "avoid", "ambiguous"):
        scores = by_kind.get(kind) or []
        if scores:
            print(f"  {kind:10s} {sum(scores) / len(scores) * 100:5.0f}%  ({len(scores)} items)")

    overall = [e.value for _, e in scored]
    print(f"\noverall selection accuracy: {sum(overall) / len(overall) * 100:.0f}%"
          f"  ({len(scored)} scored)")
    if errored:
        print(f"!! {len(errored)} item(s) EXCLUDED on transport failure, not scored: "
              f"{', '.join(i.id for i in errored)}")
        print("   A failed request returns no skill reads, which is indistinguishable "
              "from correct restraint — so these are excluded rather than scored.")

    if args.json_out:
        args.json_out.write_text(
            json.dumps(
                [
                    {
                        "id": i.id, "kind": i.kind, "subject": i.subject,
                        "expected": sorted(i.expected), "tolerated": sorted(i.tolerated),
                        "read": o.get("skill_reads", []),
                        "score": None if e is None else e.value,
                        "comment": o.get("error") if e is None else e.comment,
                        "errored": e is None,
                    }
                    for i, o, e in results
                ],
                indent=2,
            )
        )
        print(f"raw results written to {args.json_out}")


if __name__ == "__main__":
    main()
