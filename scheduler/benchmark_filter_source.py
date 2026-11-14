
#!/usr/bin/env python3
"""Benchmark production Filtering with selectable API sources."""

import io
import os
import statistics
import time
from contextlib import redirect_stdout
from unittest.mock import patch

from integrated_scheduler import eligible_nodes

ROUNDS = 20
results = {"kubectl": [], "raw": []}

# Warm-up
for source in results:
    with patch.dict(os.environ, {"SCHEDULER_API_SOURCE": source}):
        with redirect_stdout(io.StringIO()):
            eligible_nodes(250, 64)

for i in range(ROUNDS):
    order = (
        ["kubectl", "raw"]
        if i % 2 == 0
        else ["raw", "kubectl"]
    )

    decisions = {}

    for source in order:
        with patch.dict(
            os.environ,
            {"SCHEDULER_API_SOURCE": source},
        ):
            start = time.perf_counter_ns()

            with redirect_stdout(io.StringIO()):
                nodes = eligible_nodes(250, 64)

            elapsed_ms = (
                time.perf_counter_ns() - start
            ) / 1_000_000

        results[source].append(elapsed_ms)
        decisions[source] = nodes

        print(
            f"Round {i+1:02d} "
            f"{source:7} "
            f"{elapsed_ms:.3f} ms "
            f"eligible={nodes}"
        )

    assert decisions["kubectl"] == decisions["raw"], (
        f"Different Filtering results in round {i+1}"
    )

print("\n=== Production Filtering Benchmark ===")

for source, values in results.items():
    print(
        f"{source}: "
        f"mean={statistics.mean(values):.3f} ms "
        f"median={statistics.median(values):.3f} ms"
    )

old = statistics.median(results["kubectl"])
new = statistics.median(results["raw"])

print(f"Median improvement: {(old - new) / old * 100:.2f}%")
print("Note: Python process startup excluded.")

