
#!/usr/bin/env python3
"""Scheduler v8.2 - Sequential automatic scheduling."""

import argparse
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from pending_pod_scanner import scan_pending_pods

SCHEDULE_ONCE = Path(__file__).resolve().with_name(
    "schedule_once.py"
)


def timestamp():
    return datetime.now(timezone.utc).isoformat()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-pods", type=int, default=3)
    parser.add_argument("--timeout", type=int, default=180)
    parser.add_argument("--interval", type=float, default=1.0)
    args = parser.parse_args()

    if args.max_pods < 1 or args.timeout <= 0 or args.interval <= 0:
        parser.error("Arguments must be positive")

    print("=== Resource-Aware Batch Scheduler v8.2 ===", flush=True)
    print(f"Max Pods: {args.max_pods}", flush=True)
    print(f"Started: {timestamp()}", flush=True)

    deadline = time.monotonic() + args.timeout
    scheduled = 0
    seen_uids = set()

    while scheduled < args.max_pods:
        if time.monotonic() >= deadline:
            print("Timeout reached.", flush=True)
            break

        pods = scan_pending_pods()
        new_pods = [
            p for p in pods
            if p["metadata"]["uid"] not in seen_uids
        ]

        if not new_pods:
            time.sleep(args.interval)
            continue

        pod = new_pods[0]
        uid = pod["metadata"]["uid"]
        name = pod["metadata"]["name"]

        print(f"[{timestamp()}] Detected: {name}", flush=True)
        result = subprocess.run(
            [
                sys.executable,
                str(SCHEDULE_ONCE),
                "--bind",
                "--pod-uid",
                uid,
            ],
            capture_output=True,
            text=True,
        )

        print(result.stdout, flush=True)

        if result.returncode != 0:
            print(result.stderr, file=sys.stderr, flush=True)
            raise RuntimeError("Scheduling failed")

        expected = f"Binding submitted: {name} -> "

        if expected not in result.stdout:
            raise RuntimeError(
                f"Binding confirmation mismatch for {name}"
            )
        seen_uids.add(uid)
        scheduled += 1

        print(
            f"[{timestamp()}] Submitted {scheduled}/{args.max_pods}",
            flush=True,
        )

    print(f"Finished. Submitted Bindings: {scheduled}", flush=True)


if __name__ == "__main__":
    main()

