
#!/usr/bin/env python3
"""Resource-Aware Scheduler v7 - Automatic one-Pod scheduling."""

import subprocess
import time
from datetime import datetime, timezone

from pending_pod_scanner import scan_pending_pods

POLL_INTERVAL = 1
TIMEOUT_SECONDS = 120


def now():
    return datetime.now(timezone.utc).isoformat()


def main():
    print("=== Resource-Aware Auto Scheduler v7 ===", flush=True)
    print("Namespace: scheduler-lab", flush=True)
    print("Mode: Auto Binding, one Pod only", flush=True)
    print(f"Started: {now()}", flush=True)

    deadline = time.monotonic() + TIMEOUT_SECONDS

    while time.monotonic() < deadline:
        pods = scan_pending_pods()

        if pods:
            pod_name = pods[0]["metadata"]["name"]

            print(
                f"[{now()}] Detected Pending Pod: {pod_name}",
                flush=True,
            )

            result = subprocess.run(
                [
                    "python3",
                    "scheduler/schedule_once.py",
                    "--bind",
                ],
                capture_output=True,
                text=True,
            )

            print(result.stdout, flush=True)

            if result.returncode != 0:
                print(result.stderr, flush=True)
                raise RuntimeError("Scheduling failed")

            if "Binding submitted:" not in result.stdout:
                raise RuntimeError("No Binding confirmation")

            print(f"[{now()}] Scheduling submitted", flush=True)
            return

        time.sleep(POLL_INTERVAL)

    print("Timeout: no eligible Pending Pod found.")


if __name__ == "__main__":
    main()

