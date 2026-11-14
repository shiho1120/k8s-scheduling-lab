
#!/usr/bin/env python3
"""Benchmark complete Filtering with kubectl vs Raw API."""

import io
import statistics
import time
from contextlib import redirect_stdout
from unittest.mock import patch

import integrated_scheduler
from k8s_raw_client import RawKubernetesClient
from node_filter import kubectl_json

ROUNDS = 20


def main():
    raw = RawKubernetesClient()

    def kubectl_source(*args):
        return kubectl_json(*args)

    def raw_source(*args):
        if args == ("get", "nodes"):
            return raw.get_nodes()
        if args == ("get", "pods", "-A"):
            return raw.get_pods()
        raise ValueError(f"Unexpected arguments: {args}")

    methods = {
        "kubectl": kubectl_source,
        "raw_api": raw_source,
    }

    results = {
        "kubectl": [],
        "raw_api": [],
    }

    # Warm-up
    for method in methods.values():
        with patch.object(
            integrated_scheduler, "kubectl_json", method
        ):
            with redirect_stdout(io.StringIO()):
                integrated_scheduler.eligible_nodes()

    for i in range(ROUNDS):
        order = (
            ["kubectl", "raw_api"]
            if i % 2 == 0
            else ["raw_api", "kubectl"]
        )

        for name in order:
            start = time.perf_counter_ns()

            with patch.object(
                integrated_scheduler, "kubectl_json", methods[name]
            ):
                with redirect_stdout(io.StringIO()):
                    selected = integrated_scheduler.eligible_nodes(
                        request_cpu_m=250,
                        request_memory_mi=64,
                    )

            elapsed_ms = (
                time.perf_counter_ns() - start
            ) / 1_000_000

            results[name].append(elapsed_ms)

            print(
                f"Round {i+1:02d} "
                f"{name:7} "
                f"{elapsed_ms:.3f} ms "
                f"selected={selected}"
            )

    print("\n=== Complete Filtering Benchmark ===")

    for name, values in results.items():
        print(
            f"{name}: "
            f"mean={statistics.mean(values):.3f} ms "
            f"median={statistics.median(values):.3f} ms"
        )

    old = statistics.median(results["kubectl"])
    new = statistics.median(results["raw_api"])

    if old > 0:
        print(
            f"Median improvement: {(old-new)/old*100:.2f}%"
        )

    print("Note: RawKubernetesClient initialization excluded.")


if __name__ == "__main__":
    main()

