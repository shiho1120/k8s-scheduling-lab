
#!/usr/bin/env python3
"""Scheduler v5: Pending Pod Scanner (Dry Run)."""

import json
import subprocess

NAMESPACE = "scheduler-lab"
SCHEDULER_NAME = "resource-aware-scheduler"


def get_pods():
    result = subprocess.run(
        [
            "kubectl", "get", "pods",
            "-n", NAMESPACE,
            "-o", "json",
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(result.stdout)["items"]


def validate_test_pod(pod):
    spec = pod["spec"]

    if len(spec.get("containers", [])) != 1:
        return "Expected exactly one container"

    if any(spec.get(key) for key in (
        "initContainers",
        "nodeSelector",
        "affinity",
        "topologySpreadConstraints",
        "resources",
        "overhead",
    )):
        return "Unsupported Pod scheduling constraints"

    if spec.get("hostNetwork") or spec.get("hostPort"):
        return "Unsupported networking options"

    tolerations = spec.get("tolerations", [])
    allowed_keys = {
        "node.kubernetes.io/not-ready",
        "node.kubernetes.io/unreachable",
    }

    for t in tolerations:
        if (
            t.get("key") not in allowed_keys
            or t.get("effect") != "NoExecute"
            or t.get("operator") != "Exists"
        ):
            return "Unsupported tolerations"

    volumes = spec.get("volumes", [])
    for volume in volumes:
        if (
            not volume.get("name", "").startswith("kube-api-access-")
            or "projected" not in volume
        ):
            return "Unsupported volume"

    container = spec["containers"][0]

    # 固定測試工作負載：避免把掃描器誤當成通用 Scheduler。
    if container.get("image") != "nginx:stable":
        return "Unsupported test image"

    requests = container.get("resources", {}).get("requests", {})
    if requests != {"cpu": "250m", "memory": "64Mi"}:
        return "Unsupported resource requests"

    return None


def scan_pending_pods():
    candidates = []

    for pod in get_pods():
        metadata = pod["metadata"]
        spec = pod["spec"]
        status = pod.get("status", {})

        if spec.get("schedulerName") != SCHEDULER_NAME:
            continue

        if spec.get("nodeName"):
            continue

        if metadata.get("deletionTimestamp"):
            continue

        if status.get("phase") != "Pending":
            continue

        name = metadata["name"]
        reason = validate_test_pod(pod)

        if reason:
            print(f"SKIPPED: {name} ({reason})")
            continue

        candidates.append(pod)

    candidates.sort(
        key=lambda p: (
            p["metadata"].get("creationTimestamp", ""),
            p["metadata"]["name"],
        )
    )

    return candidates


def main():
    print("=== Scheduler v5: Pending Pod Scanner ===")
    print("Mode: DRY RUN")
    print(f"Namespace: {NAMESPACE}")
    print(f"Scheduler: {SCHEDULER_NAME}")
    print()

    pods = scan_pending_pods()

    if not pods:
        print("No eligible Pending Pods found.")
    else:
        for i, pod in enumerate(pods, 1):
            metadata = pod["metadata"]
            print(f"{i}. {metadata['name']}")
            print(f"   UID: {metadata['uid']}")
            print(f"   Created: {metadata['creationTimestamp']}")

    print()
    print(f"Total eligible Pending Pods: {len(pods)}")
    print("No Pod Binding performed.")


if __name__ == "__main__":
    main()

