
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
    metadata = pod["metadata"]

    image = container.get("image", "")
    requests = container.get("resources", {}).get(
        "requests", {}
    )

    # 目前兩種測試負載使用相同 Requests
    if image in ("nginx:stable", "alpine:3.20"):
        if requests != {"cpu": "250m", "memory": "64Mi"}:
            return "Unsupported resource requests"
    # v5：既有 nginx Binding 測試
    if image == "nginx:stable":
        if container.get("name") != "nginx":
            return "Unexpected nginx container"

        return None

    # v6.1：CPU Job 實驗
    if image == "alpine:3.20":
        labels = metadata.get("labels", {})

        if labels.get("experiment") != "resource-aware-v6":
            return "Missing experiment label"

        if labels.get("workload-type") != "cpu":
            return "Unsupported workload type"

        # 必須是 Kubernetes Job Controller 建立的 Pod
        owners = metadata.get("ownerReferences", [])

        if not any(
            owner.get("kind") == "Job"
            and owner.get("controller") is True
            and owner.get("apiVersion") == "batch/v1"
            for owner in owners
        ):
            return "Pod is not owned by a Job"

        if container.get("name") != "cpu":
            return "Unexpected container name"

        if container.get("command", [])[:2] != [
            "/bin/sh", "-c"
        ]:
            return "Unsupported CPU command"

        command = container.get("command", [])

        if (
            len(command) != 3
            or command[2].strip()
            != "time dd if=/dev/zero bs=1M count=1500 2>/dev/null | sha256sum"
        ):
            return "Unexpected CPU workload"

        limits = container.get("resources", {}).get(
            "limits", {}
        )

        if limits != {
            "cpu": "500m",
            "memory": "128Mi",
        }:
            return "Unexpected resource limits"

        return None

    # v6.3: Memory Job workload
    if image == "python:3.12-alpine":
        labels = metadata.get("labels", {})

        if labels.get("experiment") != "resource-aware-v6":
            return "Missing experiment label"

        if labels.get("workload-type") != "memory":
            return "Unsupported workload type"

        owners = metadata.get("ownerReferences", [])

        if not any(
            owner.get("kind") == "Job"
            and owner.get("controller") is True
            and owner.get("apiVersion") == "batch/v1"
            for owner in owners
        ):
            return "Pod is not owned by a Job"

        # 讀取既有 Baseline Memory Job 的容器規格
        from pathlib import Path
        import subprocess
        import json

        source = (
            Path(__file__).resolve().parent.parent
            / "workloads" / "memory-job.yaml"
        )

        expected_job = json.loads(
            subprocess.check_output(
                [
                    "kubectl", "create",
                    "--dry-run=client",
                    "-f", str(source),
                    "-o", "json",
                ],
                text=True,
            )
        )

        expected = (
            expected_job["spec"]["template"]["spec"]
            ["containers"][0]
        )

        # 使用與 Baseline 相同的容器、指令及資源規格
        for key in (
            "name", "image", "command", "args", "resources"
        ):
            if container.get(key) != expected.get(key):
                return f"Memory workload mismatch: {key}"

        if spec.get("restartPolicy") != "Never":
            return "Unsupported restart policy"

        return None

    return "Unsupported test image"


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

