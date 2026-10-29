
#!/usr/bin/env python3
"""Scheduler v5: schedule at most one Pending Pod per run."""

import argparse
import json

from pending_pod_scanner import (
    NAMESPACE,
    SCHEDULER_NAME,
    scan_pending_pods,
    validate_test_pod,
)
from bind_test_pod import kubectl
from integrated_scheduler import eligible_nodes
from resource_aware_scheduler import (
    query_prometheus,
    CPU_QUERY,
    MEM_QUERY,
    CPU_WEIGHT,
    MEM_WEIGHT,
    WORKERS,
)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--bind",
        action="store_true",
        help="Actually bind one Pod; default is dry run",
    )
    args = parser.parse_args()

    pods = scan_pending_pods()

    if not pods:
        print("No eligible Pending Pods.")
        return

    # 每次只選最早建立的一個 Pod
    pod = pods[0]
    name = pod["metadata"]["name"]
    uid = pod["metadata"]["uid"]

    print(f"Selected Pending Pod: {name}")
    print(f"Pod UID: {uid}")

    candidates = eligible_nodes()
    if not candidates:
        raise RuntimeError("No eligible nodes")

    cpu_data = query_prometheus(CPU_QUERY)
    mem_data = query_prometheus(MEM_QUERY)

    scored = []

    for node in candidates:
        instance = WORKERS[node]
        cpu = cpu_data.get(instance)
        mem = mem_data.get(instance)

        if cpu is None or mem is None:
            print(f"{node}: missing metrics, skipped")
            continue

        if not (0 <= cpu <= 1 and 0 <= mem <= 1):
            print(f"{node}: invalid metrics, skipped")
            continue

        score = (
            CPU_WEIGHT * (1 - cpu)
            + MEM_WEIGHT * (1 - mem)
        )

        scored.append((score, node))
        print(f"{node}: score={score:.4f}")

    if not scored:
        raise RuntimeError("No nodes with valid metrics")

    scored.sort(key=lambda item: (-item[0], item[1]))
    score, selected = scored[0]

    print(f"\nSelected Node: {selected}")
    print(f"Score: {score:.4f}")

    if not args.bind:
        print("Action: DRY RUN - NO POD BINDING")
        return

    # Binding 前重新讀取 Pod，防止誤操作已變更的 Pod
    latest = json.loads(
        kubectl(
            "get", "pod", name,
            "-n", NAMESPACE, "-o", "json"
        )
    )

    if latest["metadata"]["uid"] != uid:
        raise RuntimeError("Pod UID changed")

    if latest["metadata"].get("deletionTimestamp"):
        raise RuntimeError("Pod is being deleted")

    if latest["spec"].get("nodeName"):
        raise RuntimeError("Pod is already bound")

    if latest["spec"].get("schedulerName") != SCHEDULER_NAME:
        raise RuntimeError("Unexpected schedulerName")

    if latest.get("status", {}).get("phase") != "Pending":
        raise RuntimeError("Pod is no longer Pending")

    if validate_test_pod(latest) is not None:
        raise RuntimeError("Pod specification is unsupported")

    # 防止掃描後 Pod 規格被修改
    if (
        latest["metadata"]["resourceVersion"]
        != pod["metadata"]["resourceVersion"]
    ):
        raise RuntimeError("Pod changed since initial scan")

    binding = {
        "apiVersion": "v1",
        "kind": "Binding",
        "metadata": {
            "name": name,
            "namespace": NAMESPACE,
            "uid": uid,
        },
        "target": {
            "apiVersion": "v1",
            "kind": "Node",
            "name": selected,
        },
    }

    path = (
        f"/api/v1/namespaces/{NAMESPACE}"
        f"/pods/{name}/binding"
    )

    kubectl(
        "create", "--raw", path, "-f", "-",
        payload=binding,
    )

    print(f"Binding submitted: {name} -> {selected}")


if __name__ == "__main__":
    main()

