
#!/usr/bin/env python3
"""Scheduler v5: schedule at most one Pending Pod per run."""

import argparse
import json
import time
from experiment_logger import log_experiment
from node_filter import pod_requests
from decision_logger import log_decision
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
    parser.add_argument(
        "--pod-uid",
        default=None,
        help="Schedule only the Pod matching this UID",
    )

    args = parser.parse_args()
    start_ns = time.perf_counter_ns()
    pods = scan_pending_pods()

    if args.pod_uid:
        pods = [
            pod for pod in pods
            if pod["metadata"]["uid"] == args.pod_uid
        ]

        if len(pods) != 1:
            raise RuntimeError(
                f"Target Pod UID not eligible: {args.pod_uid}"
            )

    if not pods:
        print("No eligible Pending Pods.")
        return

    # 指定 UID 時使用指定 Pod，否則維持原本行為
    pod = pods[0]
    name = pod["metadata"]["name"]
    uid = pod["metadata"]["uid"]

    print(f"Selected Pending Pod: {name}")
    print(f"Pod UID: {uid}")

        # 根據目前待排程 Pod 的實際 Requests 進行過濾
    request_cpu_m, request_memory_mi = pod_requests(pod)

    print(
        f"Pod Requests: CPU={request_cpu_m:.0f}m, "
        f"Memory={request_memory_mi:.0f}Mi"
    )

    filter_start_ns = time.perf_counter_ns()
    candidates = eligible_nodes(
        request_cpu_m=request_cpu_m,
        request_memory_mi=request_memory_mi,
    )
    filter_end_ns = time.perf_counter_ns()
    if not candidates:
        raise RuntimeError("No eligible nodes")

    score_start_ns = time.perf_counter_ns()
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

        scored.append((score, node, cpu, mem))
        print(f"{node}: score={score:.4f}")

    if not scored:
        raise RuntimeError("No nodes with valid metrics")

    scored.sort(key=lambda item: (-item[0], item[1]))
    score, selected, selected_cpu, selected_mem = scored[0]
    score_end_ns = time.perf_counter_ns()
    candidate_scores = [
    {
        "node": node,
        "cpu_usage": cpu,
        "memory_usage": mem,
        "score": round(node_score, 6),
    }
    for node_score, node, cpu, mem in scored
    ] 
    print(f"\nSelected Node: {selected}")
    print(f"Score: {score:.4f}")

    if not args.bind:
        log_decision(
            pod_namespace=NAMESPACE,
            pod_name=name,
            pod_uid=uid,
            selected_node=selected,
            cpu_usage=selected_cpu,
            memory_usage=selected_mem,
            score=score,
            action="dry_run",
            result="dry_run",
        )   

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

    bind_start_ns = time.perf_counter_ns()

    try:
        kubectl(
            "create", "--raw", path, "-f", "-",
            payload=binding,
        )
        bind_end_ns = time.perf_counter_ns()
    except Exception as exc:
        log_decision(
            pod_namespace=NAMESPACE,
            pod_name=name,
            pod_uid=uid,
            selected_node=selected,
            cpu_usage=selected_cpu,
            memory_usage=selected_mem,
            score=score,
            action="bind",
            result="failed",
            error=str(exc),
        )
        raise
    # Binding API 已成功返回
    print(f"Binding submitted: {name} -> {selected}", flush=True)

    try:
        log_decision(
            pod_namespace=NAMESPACE,
            pod_name=name,
            pod_uid=uid,
            selected_node=selected,
            cpu_usage=selected_cpu,
            memory_usage=selected_mem,
            score=score,
            action="bind",
            result="submitted",
        )

        log_experiment(
            pod_namespace=NAMESPACE,
            pod_name=name,
            pod_uid=uid,
            selected_node=selected,
            filter_duration_ms=(
                filter_end_ns - filter_start_ns
            ) / 1_000_000,
            score_duration_ms=(
                score_end_ns - score_start_ns
            ) / 1_000_000,
            bind_duration_ms=(
                bind_end_ns - bind_start_ns
            ) / 1_000_000,
            total_duration_ms=(
                bind_end_ns - start_ns
            ) / 1_000_000,
            candidate_scores=candidate_scores,
            result="submitted",
        )

    except Exception as exc:
        print(
            f"WARNING: Binding submitted, but logging failed: {exc}",
            flush=True,
        )

if __name__ == "__main__":
    main()

