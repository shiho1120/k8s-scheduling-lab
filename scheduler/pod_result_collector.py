
#!/usr/bin/env python3
"""Collect Kubernetes Pod scheduling and execution timestamps."""

import csv
import json
import subprocess
from pathlib import Path

NAMESPACE = "scheduler-lab"
SCHEDULER_NAME = "resource-aware-scheduler"

OUTPUT = (
    Path(__file__).resolve().parent.parent
    / "results" / "scheduler-v5-2" / "pod-results.csv"
)

FIELDS = [
    "pod",
    "pod_uid",
    "scheduler",
    "node",
    "phase",
    "created_at",
    "scheduled_at",
    "container_started_at",
    "container_finished_at",
]


def get_pods():
    result = subprocess.run(
        ["kubectl", "get", "pods", "-n", NAMESPACE, "-o", "json"],
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(result.stdout)["items"]


def scheduled_at(pod):
    for condition in pod.get("status", {}).get("conditions", []):
        if (
            condition.get("type") == "PodScheduled"
            and condition.get("status") == "True"
        ):
            return condition.get("lastTransitionTime", "")

    return ""


def container_times(pod):
    starts = []
    finishes = []

    for container in pod.get("status", {}).get(
        "containerStatuses", []
    ):
        state = container.get("state", {})

        terminated = state.get("terminated", {})
        running = state.get("running", {})

        started = (
            terminated.get("startedAt")
            or running.get("startedAt")
        )

        finished = terminated.get("finishedAt")

        if started:
            starts.append(started)

        if finished:
            finishes.append(finished)

    return (
        min(starts) if starts else "",
        max(finishes) if finishes else "",
    )


def main():
    rows = []

    for pod in get_pods():
        metadata = pod["metadata"]
        spec = pod["spec"]
        status = pod.get("status", {})

        if spec.get("schedulerName") != SCHEDULER_NAME:
            continue

        started, finished = container_times(pod)

        rows.append({
            "pod": metadata["name"],
            "pod_uid": metadata["uid"],
            "scheduler": spec.get("schedulerName", ""),
            "node": spec.get("nodeName", ""),
            "phase": status.get("phase", ""),
            "created_at": metadata.get("creationTimestamp", ""),
            "scheduled_at": scheduled_at(pod),
            "container_started_at": started,
            "container_finished_at": finished,
        })

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)

    with OUTPUT.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)

    print(f"Collected {len(rows)} Pods")
    print(f"CSV saved: {OUTPUT}")


if __name__ == "__main__":
    main()

