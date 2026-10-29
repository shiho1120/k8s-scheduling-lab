
#!/usr/bin/env python3
"""Resource-Aware Scheduler v2: Node Filtering Dry Run.

適用於目前實驗中的簡單 CPU / Memory 工作負載。
只讀取 Kubernetes API，不執行 Pod Binding。
"""

import json
import subprocess

WORKERS = [
    "k8s-worker1",
    "k8s-worker2",
    "k8s-worker3",
]

# 模擬待排程的 CPU Job
REQUEST_CPU_M = 250
REQUEST_MEMORY_MI = 64


def kubectl_json(*args):
    result = subprocess.run(
        ["kubectl", *args, "-o", "json"],
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(result.stdout)


def cpu_millicores(value):
    value = str(value)
    if value.endswith("m"):
        return float(value[:-1])
    return float(value) * 1000


def memory_mi(value):
    value = str(value)
    suffixes = {
        "Ki": 1 / 1024,
        "Mi": 1,
        "Gi": 1024,
        "Ti": 1024 * 1024,
        "K": 1000 / (1024 * 1024),
        "M": 1000**2 / (1024**2),
        "G": 1000**3 / (1024**2),
    }

    for suffix in sorted(suffixes, key=len, reverse=True):
        if value.endswith(suffix):
            return float(value[:-len(suffix)]) * suffixes[suffix]

    return float(value) / (1024 * 1024)



def pod_requests(pod):
    spec = pod["spec"]

    # v2 暫不支援 Pod-level resource requests。
    # 避免錯誤估算 Kubernetes 1.35 的複雜資源規則。
    if spec.get("resources", {}).get("requests"):
        raise ValueError("Pod-level resources not supported yet")

    def requests_of(container):
        req = container.get("resources", {}).get("requests", {})
        return (
            cpu_millicores(req.get("cpu", "0")),
            memory_mi(req.get("memory", "0")),
        )

    # 一般應用容器的 Requests 加總
    app_cpu = 0
    app_mem = 0

    for container in spec.get("containers", []):
        cpu, mem = requests_of(container)
        app_cpu += cpu
        app_mem += mem

    # 一般 Init Containers 依序執行。
    # 但 restartPolicy=Always 是持續執行的 Sidecar，
    # v2 尚未支援其不同的資源計算方式。
    init_cpu = 0
    init_mem = 0

    for container in spec.get("initContainers", []):
        if container.get("restartPolicy") == "Always":
            raise ValueError(
                "Restartable init sidecar not supported yet"
            )

        cpu, mem = requests_of(container)
        init_cpu = max(init_cpu, cpu)
        init_mem = max(init_mem, mem)

    # 每種資源分別取較大的值
    effective_cpu = max(app_cpu, init_cpu)
    effective_mem = max(app_mem, init_mem)

    # Pod Overhead 需要額外計入
    overhead = spec.get("overhead", {})

    effective_cpu += cpu_millicores(
        overhead.get("cpu", "0")
    )
    effective_mem += memory_mi(
        overhead.get("memory", "0")
    )

    return effective_cpu, effective_mem


def main():
    nodes = kubectl_json("get", "nodes")["items"]
    pods = kubectl_json("get", "pods", "-A")["items"]

    print("=== Resource-Aware Node Filtering ===")
    print(f"CPU Request: {REQUEST_CPU_M}m")
    print(f"Memory Request: {REQUEST_MEMORY_MI}Mi")
    print("Mode: DRY RUN\n")

    candidates = []

    for node in nodes:
        name = node["metadata"]["name"]

        if name not in WORKERS:
            continue

        spec = node.get("spec", {})
        conditions = node["status"].get("conditions", [])

        ready = any(
            c["type"] == "Ready" and c["status"] == "True"
            for c in conditions
        )

        reasons = []

        if not ready:
            reasons.append("Node NotReady")

        if spec.get("unschedulable", False):
            reasons.append("Node Unschedulable")

        if spec.get("taints"):
            reasons.append("Node has taints (no toleration support yet)")

        allocatable = node["status"]["allocatable"]

        total_cpu = cpu_millicores(allocatable["cpu"])
        total_mem = memory_mi(allocatable["memory"])

        used_cpu = 0
        used_mem = 0

        for pod in pods:
            pod_spec = pod["spec"]
            phase = pod.get("status", {}).get("phase")

            if pod_spec.get("nodeName") != name:
                continue

            if phase in ("Succeeded", "Failed"):
                continue

            try:
                cpu, mem = pod_requests(pod)
            except ValueError as exc:
                reasons.append(
                    f"Unsupported existing Pod: "
                    f"{pod['metadata']['name']} ({exc})"
                )
                continue

            used_cpu += cpu
            used_mem += mem

        free_cpu = total_cpu - used_cpu
        free_mem = total_mem - used_mem

        if free_cpu < REQUEST_CPU_M:
            reasons.append("Insufficient CPU")

        if free_mem < REQUEST_MEMORY_MI:
            reasons.append("Insufficient Memory")

        print(f"Node: {name}")
        print(f"  Allocatable CPU: {total_cpu:.0f}m")
        print(f"  Requested CPU:   {used_cpu:.0f}m")
        print(f"  Remaining CPU:   {free_cpu:.0f}m")
        print(f"  Remaining Mem:   {free_mem:.0f}Mi")

        if reasons:
            print(f"  Result: REJECTED ({'; '.join(reasons)})")
        else:
            print("  Result: ELIGIBLE")
            candidates.append(name)

        print()

    print("=== Eligible Nodes ===")
    print(", ".join(candidates) if candidates else "None")
    print("No Pod Binding performed.")


if __name__ == "__main__":
    main()

