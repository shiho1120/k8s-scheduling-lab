
#!/usr/bin/env python3
"""Read Kubernetes Nodes and Pods as raw JSON."""

import json

from kubernetes import client, config


class RawKubernetesClient:
    def __init__(self):
        config.load_kube_config()
        self.api = client.CoreV1Api()

    def _read_json(self, method):
        response = method(_preload_content=False)

        try:
            return json.loads(response.data)
        finally:
            response.close()
            response.release_conn()

    def get_nodes(self):
        return self._read_json(self.api.list_node)

    def get_pods(self):
        return self._read_json(
            self.api.list_pod_for_all_namespaces
        )

