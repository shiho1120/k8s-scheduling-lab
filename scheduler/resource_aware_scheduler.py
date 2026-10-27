
#!/usr/bin/env python3
"""Resource-Aware Scheduler v1 - Dry Run."""

import json
import math
import time
from urllib.parse import urlencode
from urllib.request import urlopen

PROMETHEUS_URL = "http://127.0.0.1:9090"

WORKERS = {
    "k8s-worker1": "192.168.29.11:9100",
    "k8s-worker2": "192.168.29.12:9100",
    "k8s-worker3": "192.168.29.13:9100",
}

CPU_WEIGHT = 0.6
MEM_WEIGHT = 0.4
MAX_METRIC_AGE = 120  # 秒

CPU_QUERY = (
    '1 - avg by(instance) ('
    'rate(node_cpu_seconds_total'
    '{job="node-exporter",mode="idle"}[5m]))'
)

MEM_QUERY = (
    '1 - ('
    'node_memory_MemAvailable_bytes{job="node-exporter"}'
    ' / '
    'node_memory_MemTotal_bytes{job="node-exporter"}'
    ')'
)


def query_prometheus(promql):
    params = urlencode({"query": promql})
    url = f"{PROMETHEUS_URL}/api/v1/query?{params}"

    with urlopen(url, timeout=10) as response:
        payload = json.load(response)

    if payload.get("status") != "success":
        raise RuntimeError(f"Prometheus query failed: {payload}")

    result = {}

    for item in payload["data"]["result"]:
        instance = item["metric"].get("instance")
        timestamp, raw_value = item["value"]
        value = float(raw_value)

        if not math.isfinite(value):
            continue

        if time.time() - float(timestamp) > MAX_METRIC_AGE:
            continue

        result[instance] = value

    return result


def main():
    print("=== Resource-Aware Scheduler v1 ===")
    print("Mode: DRY RUN (No Pod Binding)")
    print()

    cpu_usage = query_prometheus(CPU_QUERY)
    mem_usage = query_prometheus(MEM_QUERY)

    candidates = []

    for node, instance in WORKERS.items():
        cpu = cpu_usage.get(instance)
        mem = mem_usage.get(instance)

        if cpu is None or mem is None:
            print(f"{node}: Missing or stale metrics, skipped")
            continue

        if not (0 <= cpu <= 1 and 0 <= mem <= 1):
            print(f"{node}: Invalid utilization values, skipped")
            continue

        score = (
            CPU_WEIGHT * (1 - cpu)
            + MEM_WEIGHT * (1 - mem)
        )

        print(f"Node: {node}")
        print(f"  CPU Usage:    {cpu * 100:.2f}%")
        print(f"  Memory Usage: {mem * 100:.2f}%")
        print(f"  Score:        {score:.4f}")
        print()

        candidates.append((score, node))

    if not candidates:
        raise RuntimeError("No nodes with valid metrics")

    candidates.sort(key=lambda item: (-item[0], item[1]))
    best_score, best_node = candidates[0]

    print("=== Scheduling Decision ===")
    print(f"Selected Node: {best_node}")
    print(f"Score: {best_score:.4f}")
    print("Action: DRY RUN ONLY")


if __name__ == "__main__":
    main()

