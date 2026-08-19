#!/usr/bin/env python3
"""Replay debug dumps through the parser and report what it decodes.

Any protocol change should be checked against previously captured traffic
before release. A decode that changes unintentionally is the signal that
something regressed; the tool reports totals so a diff between runs is obvious.

    python3 tools/replay_debug.py dumps/*.json
    python3 tools/replay_debug.py --baseline before.json dumps/*.json
"""
from __future__ import annotations

import argparse
import glob
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _frames import frames_from_debug, proto  # noqa: E402


def summarise(paths: list[str]) -> dict:
    totals = Counter()
    events = Counter()
    unparsed: list[str] = []

    for path in paths:
        dump = json.load(open(path))
        for entry in dump.get("recent_frames", []):
            hexs = entry.get("hex") or ""
            if len(hexs) < 14:
                continue
            try:
                raw = bytes.fromhex(hexs)
            except ValueError:
                continue
            totals["frames"] += 1
            if proto.parse_frame(raw) is None:
                totals["unparsed"] += 1
                # A frame the panel sent that we cannot read is exactly the
                # symptom of a framing bug, so surface examples not just counts.
                if len(unparsed) < 5:
                    unparsed.append(hexs)

        for item in frames_from_debug(path):
            body = item["frame"].body
            if proto.parse_input_status_response(body):
                totals["input_status"] += 1
            elif proto.parse_door_status_response(body):
                totals["door_status"] += 1
            elif proto.parse_area_status_response(body):
                totals["area_status"] += 1
            elif proto.parse_relay_status_response(body):
                totals["relay_status"] += 1
            elif proto.parse_user_records(body):
                totals["user_records"] += 1
            else:
                ev = proto.parse_event_full(body)
                if ev:
                    totals["events"] += 1
                    events[f"0x{ev['code']:02X}"] += 1
                    if not ev["anchored"]:
                        totals["events_unanchored"] += 1

    return {"totals": dict(totals), "events": dict(events), "unparsed_examples": unparsed}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("dumps", nargs="+", help="debug dump JSON files or globs")
    ap.add_argument("--baseline", help="compare against a previously saved summary")
    ap.add_argument("--save", help="write the summary for use as a future baseline")
    args = ap.parse_args()

    paths: list[str] = []
    for pattern in args.dumps:
        paths.extend(sorted(glob.glob(pattern)) or [pattern])

    result = summarise(paths)
    print(f"Replayed {len(paths)} dump(s)\n")
    for k, v in sorted(result["totals"].items()):
        print(f"  {k:22} {v}")
    if result["events"]:
        print("\n  event codes seen:")
        for code, n in sorted(result["events"].items()):
            print(f"    {code}  x{n}")
    if result["unparsed_examples"]:
        print("\n  unparsed examples:")
        for h in result["unparsed_examples"]:
            print(f"    {h}")

    if args.save:
        json.dump(result, open(args.save, "w"), indent=2, sort_keys=True)
        print(f"\nSummary written to {args.save}")

    if args.baseline:
        old = json.load(open(args.baseline))
        changed = {k: (old["totals"].get(k), result["totals"].get(k))
                   for k in set(old["totals"]) | set(result["totals"])
                   if old["totals"].get(k) != result["totals"].get(k)}
        print()
        if changed:
            print("CHANGED against baseline:")
            for k, (a, b) in sorted(changed.items()):
                print(f"  {k}: {a} -> {b}")
            print("\nIf this was not intended, something regressed.")
            return 1
        print("No change against baseline")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
