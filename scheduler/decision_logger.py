
#!/usr/bin/env python3
"""Scheduler v5.1 - Scheduling Decision CSV Logger."""

import csv
import os
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

LOG_PATH = Path(
    os.environ.get(
        "SCHEDULER_LOG_PATH",
        str(PROJECT_ROOT / "results" / "scheduler-v5-1" / "decisions.csv"),
    )
)

FIELDS = [
    "timestamp",
    "scheduler_version",
    "pod_namespace",
    "pod_name",
    "pod_uid",
    "selected_node",
    "cpu_usage",
    "memory_usage",
    "score",
    "action",
    "result",
    "error",
]


def log_decision(
    pod_namespace,
    pod_name,
    pod_uid,
    selected_node="",
    cpu_usage=None,
    memory_usage=None,
    score=None,
    action="dry_run",
    result="",
    error="",
):
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)

    row = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "scheduler_version": "v5.1",
        "pod_namespace": pod_namespace,
        "pod_name": pod_name,
        "pod_uid": pod_uid,
        "selected_node": selected_node,
        "cpu_usage": cpu_usage,
        "memory_usage": memory_usage,
        "score": score,
        "action": action,
        "result": result,
        "error": error,
    }

    # 先以單一 Scheduler 程序執行為前提。
    # 不支援多程序同時寫入同一 CSV。
    with LOG_PATH.open("a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)

        if f.tell() == 0:
            writer.writeheader()

        writer.writerow(row)
        f.flush()
        os.fsync(f.fileno())

    print(f"Decision logged: {LOG_PATH}")

