
#!/usr/bin/env python3
"""One-shot resource-aware Pod Binding test."""

import json
import subprocess

from integrated_scheduler import eligible_nodes
from resource_aware_scheduler import (
    query_prometheus,
    CPU_QUERY,
    MEM_QUERY,
    CPU_WEIGHT,
    MEM_WEIGHT,
    WORKERS,
)

NAMESPACE = "scheduler-lab"
POD_NAME = "resource-aware-test"
SCHEDULER_NAME = "resource-aware-scheduler"


def kubectl(*args, payload=None):
    result = subprocess.run(
        ["kubectl", *args],
        input=json.dumps(payload) if payload else None,
        text=True,
        capture_output=True,
        check=True,
    )
    return result.stdout


def main():
    pod = json.loads(
        kubectl(
            "get", "pod", POD_NAME,
            "-n", NAMESPACE, "-o", "json"
        )
    )

    spec = pod["spec"]

    if spec.get("schedulerName") != SCHEDULER_NAME:
        raise RuntimeError("Unexpected schedulerName")

    if spec.get("nodeName"):
        raise RuntimeError("Pod is already bound")


    # 僅允許 Kubernetes 自動加入的兩種預設 tolerations
    tolerations = spec.get("tolerations", [])
    allowed_keys = {
        "node.kubernetes.io/not-ready",
        "node.kubernetes.io/unreachable",
    }

    if any(
        t.get("key") not in allowed_keys
        or t.get("effect") != "NoExecute"
        or t.get("operator") != "Exists"
        for t in tolerations
    ):
        raise RuntimeError("Unsupported tolerations")

    # 僅允許預設的 ServiceAccount projected volume
    volumes = spec.get("volumes", [])
    if any(
        not v.get("name", "").startswith("kube-api-access-")
        or "projected" not in v
        for v in volumes
    ):
        raise RuntimeError("Unsupported volumes")

    if (
        len(spec["containers"]) != 1
        or spec.get("initContainers")
        or spec.get("nodeSelector")
        or spec.get("affinity")
        or spec.get("topologySpreadConstraints")
        or spec.get("resources")
        or spec.get("overhead")
        or spec.get("nodeName")
    ):
        raise RuntimeError("Unsupported test Pod specification")

    requests = spec["containers"][0]["resources"]["requests"]

    if requests != {"cpu": "250m", "memory": "64Mi"}:
        raise RuntimeError("Unexpected Pod resource requests")

    candidates = eligible_nodes()

    cpu_data = query_prometheus(CPU_QUERY)
    mem_data = query_prometheus(MEM_QUERY)

    scored = []

    for node in candidates:
        instance = WORKERS[node]
        cpu = cpu_data.get(instance)
        mem = mem_data.get(instance)

        if cpu is None or mem is None:
            continue

        if not (0 <= cpu <= 1 and 0 <= mem <= 1):
            continue

        score = (
            CPU_WEIGHT * (1 - cpu)
            + MEM_WEIGHT * (1 - mem)
        )

        scored.append((score, node))
        print(f"{node}: score={score:.4f}")

    if not scored:
        raise RuntimeError("No eligible node with valid metrics")

    scored.sort(key=lambda x: (-x[0], x[1]))
    score, selected = scored[0]

    print(f"\nSelected Node: {selected}")

    # 再次確認目標 Pod 尚未被排程
    latest = json.loads(
        kubectl(
            "get", "pod", POD_NAME,
            "-n", NAMESPACE, "-o", "json"
        )
    )

    if (
        latest["metadata"]["uid"] != pod["metadata"]["uid"]
        or latest["spec"].get("nodeName")
        or latest.get("metadata", {}).get("deletionTimestamp")
    ):
        raise RuntimeError("Pod changed before binding")

    binding = {
        "apiVersion": "v1",
        "kind": "Binding",
        "metadata": {
            "name": POD_NAME,
            "namespace": NAMESPACE,
            "uid": pod["metadata"]["uid"],
        },
        "target": {
            "apiVersion": "v1",
            "kind": "Node",
            "name": selected,
        },
    }

    path = (
        f"/api/v1/namespaces/{NAMESPACE}"
        f"/pods/{POD_NAME}/binding"
    )

    kubectl("create", "--raw", path, "-f", "-", payload=binding)

    print(f"Binding submitted: {POD_NAME} -> {selected}")
    print(f"Decision score: {score:.4f}")


if __name__ == "__main__":
    main()

