
#!/usr/bin/env python3
"""Measure first-use Raw API initialization and filtering cost."""

import time

start = time.perf_counter_ns()

from k8s_raw_client import RawKubernetesClient

after_import = time.perf_counter_ns()

api = RawKubernetesClient()

after_init = time.perf_counter_ns()

nodes = api.get_nodes()
pods = api.get_pods()

after_query = time.perf_counter_ns()

print("Nodes:", len(nodes["items"]))
print("Pods:", len(pods["items"]))

print(
    "Import:",
    round((after_import - start) / 1_000_000, 3),
    "ms"
)

print(
    "Client initialization:",
    round((after_init - after_import) / 1_000_000, 3),
    "ms"
)

print(
    "API queries:",
    round((after_query - after_init) / 1_000_000, 3),
    "ms"
)

print(
    "Total:",
    round((after_query - start) / 1_000_000, 3),
    "ms"
)

