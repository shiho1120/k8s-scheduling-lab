
#!/usr/bin/env python3
"""Resource-Aware Scheduler v3: Filtering + Scoring Dry Run."""

from node_filter import (
    kubectl_json,
    cpu_millicores,
    memory_mi,
    pod_requests,
    WORKERS,
    REQUEST_CPU_M,
    REQUEST_MEMORY_MI,
)

from resource_aware_scheduler import (
    query_prometheus,
    CPU_QUERY,
    MEM_QUERY,
    CPU_WEIGHT,
    MEM_WEIGHT,
    WORKERS as METRIC_INSTANCES,
)


def eligible_nodes():
    nodes = kubectl_json("get", "nodes")["items"]
    pods = kubectl_json("get", "pods", "-A")["items"]

    eligible = []

    for node in nodes:
        name = node["metadata"]["name"]

        if name not in WORKERS:
            continue

        reasons = []
        spec = node.get("spec", {})

        ready = any(
            c["type"] == "Ready" and c["status"] == "True"
            for c in node["status"].get("conditions", [])
        )

        if not ready:
            reasons.append("NotReady")

        if spec.get("unschedulable", False):
            reasons.append("Unschedulable")

        # v3 尚未實作 Tolerations，保守排除有 Taints 的節點
        if spec.get("taints"):
            reasons.append("Taints not supported")

        capacity = node["status"]["allocatable"]
        cpu_total = cpu_millicores(capacity["cpu"])
        mem_total = memory_mi(capacity["memory"])

        cpu_used = 0
        mem_used = 0

        for pod in pods:
            if pod["spec"].get("nodeName") != name:
                continue

            if pod.get("status", {}).get("phase") in (
                "Succeeded", "Failed"
            ):
                continue

            try:
                cpu, mem = pod_requests(pod)
                cpu_used += cpu
                mem_used += mem
            except ValueError as exc:
                reasons.append(
                    f"Unsupported Pod "
                    f"{pod['metadata']['name']}: {exc}"
                )

        cpu_free = cpu_total - cpu_used
        mem_free = mem_total - mem_used

        if cpu_free < REQUEST_CPU_M:
            reasons.append("Insufficient CPU")

        if mem_free < REQUEST_MEMORY_MI:
            reasons.append("Insufficient Memory")

        print(
            f"{name}: free CPU={cpu_free:.0f}m, "
            f"free memory={mem_free:.0f}Mi"
        )

        if reasons:
            print("  REJECTED:", "; ".join(reasons))
        else:
            print("  ELIGIBLE")
            eligible.append(name)

    return eligible


def main():
    print("=== Resource-Aware Scheduler v3 ===")
    print("Mode: FILTERING + SCORING DRY RUN")
    print()

    candidates = eligible_nodes()

    if not candidates:
        print("\nNo eligible nodes. No scheduling decision.")
        return

    cpu_data = query_prometheus(CPU_QUERY)
    mem_data = query_prometheus(MEM_QUERY)

    scores = []

    print("\n=== Node Scoring ===")

    for node in candidates:
        instance = METRIC_INSTANCES[node]

        cpu = cpu_data.get(instance)
        mem = mem_data.get(instance)

        if cpu is None or mem is None:
            print(f"{node}: Missing or stale metrics, skipped")
            continue

        if not (0 <= cpu <= 1 and 0 <= mem <= 1):
            print(f"{node}: Invalid metrics, skipped")
            continue

        score = (
            CPU_WEIGHT * (1 - cpu)
            + MEM_WEIGHT * (1 - mem)
        )

        scores.append((score, node))

        print(
            f"{node}: CPU={cpu * 100:.2f}%, "
            f"MEM={mem * 100:.2f}%, "
            f"SCORE={score:.4f}"
        )

    if not scores:
        print("\nNo nodes with valid metrics.")
        return

    scores.sort(key=lambda item: (-item[0], item[1]))
    best_score, best_node = scores[0]

    print("\n=== Final Scheduling Decision ===")
    print(f"Selected Node: {best_node}")
    print(f"Score: {best_score:.4f}")
    print("Action: DRY RUN ONLY - NO POD BINDING")


if __name__ == "__main__":
    main()

