
#!/usr/bin/env python3
"""Merge scheduling decisions and Pod execution results."""

import csv
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

DECISIONS = ROOT / "results/scheduler-v5-1/decisions.csv"
PODS = ROOT / "results/scheduler-v5-2/pod-results.csv"
OUTPUT = ROOT / "results/scheduler-v5-2/experiment-results.csv"


def duration_seconds(start, end):
    if not start or not end:
        return ""

    a = datetime.fromisoformat(start.replace("Z", "+00:00"))
    b = datetime.fromisoformat(end.replace("Z", "+00:00"))

    return round((b - a).total_seconds(), 3)


def read_csv(path):
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def main():
    decisions = read_csv(DECISIONS)
    pods = read_csv(PODS)

    # 只使用 Binding API 已成功回應的決策。
    # 同一 Pod 若存在重複紀錄，取最後一筆。
    bindings = {}

    for decision in decisions:
        if (
            decision["action"] == "bind"
            and decision["result"] == "submitted"
        ):
            bindings[decision["pod_uid"]] = decision

    results = []

    for pod in pods:
        decision = bindings.get(pod["pod_uid"])

        if not decision:
            continue

        scheduling_wait = duration_seconds(
            pod["created_at"],
            pod["scheduled_at"],
        )

        startup_wait = duration_seconds(
            pod["scheduled_at"],
            pod["container_started_at"],
        )

        execution_time = duration_seconds(
            pod["container_started_at"],
            pod["container_finished_at"],
        )

        is_valid = pod["phase"] == "Succeeded"

        results.append({
            "pod": pod["pod"],
            "pod_uid": pod["pod_uid"],
            "scheduler": pod["scheduler"],
            "selected_node": decision["selected_node"],
            "actual_node": pod["node"],
            "cpu_usage": decision["cpu_usage"],
            "memory_usage": decision["memory_usage"],
            "score": decision["score"],
            "phase": pod["phase"],
            "scheduling_wait_sec": scheduling_wait,
            "startup_wait_sec": startup_wait,
            "execution_sec": execution_time,
            "valid_for_comparison": is_valid,
        })

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)

    fields = [
        "pod",
        "pod_uid",
        "scheduler",
        "selected_node",
        "actual_node",
        "cpu_usage",
        "memory_usage",
        "score",
        "phase",
        "scheduling_wait_sec",
        "startup_wait_sec",
        "execution_sec",
        "valid_for_comparison",
    ]

    with OUTPUT.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(results)

    print(f"Merged {len(results)} Pod records")
    print(f"Output: {OUTPUT}")


if __name__ == "__main__":
    main()

