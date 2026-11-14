
#!/usr/bin/env python3
"""Compare Filtering results using kubectl and Raw API data."""

import io
from contextlib import redirect_stdout
from unittest.mock import patch

import integrated_scheduler
from node_filter import kubectl_json
from k8s_raw_client import RawKubernetesClient


def run_filter(nodes, pods, cpu, memory):
    def fake_kubectl(*args):
        if args == ("get", "nodes"):
            return nodes
        if args == ("get", "pods", "-A"):
            return pods
        raise RuntimeError(f"Unexpected call: {args}")

    output = io.StringIO()

    with patch.object(
        integrated_scheduler, "kubectl_json", fake_kubectl
    ):
        with redirect_stdout(output):
            selected = integrated_scheduler.eligible_nodes(
                request_cpu_m=cpu,
                request_memory_mi=memory,
            )

    return selected, output.getvalue()


def main():
    raw = RawKubernetesClient()

    kubectl_nodes = kubectl_json("get", "nodes")
    kubectl_pods = kubectl_json("get", "pods", "-A")

    raw_nodes = raw.get_nodes()
    raw_pods = raw.get_pods()

    print("kubectl Nodes:", len(kubectl_nodes["items"]))
    print("Raw API Nodes:", len(raw_nodes["items"]))
    print("kubectl Pods:", len(kubectl_pods["items"]))
    print("Raw API Pods:", len(raw_pods["items"]))

    for cpu, memory in [
        (250, 64),
        (100, 256),
        (1000, 512),
    ]:
        before, before_output = run_filter(
            kubectl_nodes, kubectl_pods, cpu, memory
        )

        after, after_output = run_filter(
            raw_nodes, raw_pods, cpu, memory
        )

        assert before == after, (
            f"Eligible nodes differ: {before} != {after}"
        )

        assert before_output == after_output, (
            f"Filtering diagnostics differ for {cpu}m/{memory}Mi"
        )

        print(f"PASS {cpu}m/{memory}Mi: {after}")

    print("Raw API Filtering equivalence passed.")


if __name__ == "__main__":
    main()

