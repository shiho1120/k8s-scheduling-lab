
#!/usr/bin/env python3
"""Scheduler v8.1 - Experiment timing and candidate logger."""

import csv
import json
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

LOG_PATH = (
    PROJECT_ROOT
    / "results"
    / "resource-aware-v8"
    / "scheduling-timing.csv"
)

FIELDS = [
    "timestamp",
    "pod_namespace",
    "pod_name",
    "pod_uid",
    "selected_node",
    "filter_duration_ms",
    "score_duration_ms",
    "bind_duration_ms",
    "total_duration_ms",
    "candidate_scores",
    "result",
]


def log_experiment(
    pod_namespace,
    pod_name,
    pod_uid,
    selected_node,
    filter_duration_ms,
    score_duration_ms,
    bind_duration_ms,
    total_duration_ms,
    candidate_scores,
    result,
):
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)

    row = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "pod_namespace": pod_namespace,
        "pod_name": pod_name,
        "pod_uid": pod_uid,
        "selected_node": selected_node,
        "filter_duration_ms": round(filter_duration_ms, 3),
        "score_duration_ms": round(score_duration_ms, 3),
        "bind_duration_ms": round(bind_duration_ms, 3),
        "total_duration_ms": round(total_duration_ms, 3),
        "candidate_scores": json.dumps(
            candidate_scores, sort_keys=True
        ),
        "result": result,
    }

    with LOG_PATH.open("a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)

        if f.tell() == 0:
            writer.writeheader()

        writer.writerow(row)

    print(f"Experiment logged: {LOG_PATH}")

