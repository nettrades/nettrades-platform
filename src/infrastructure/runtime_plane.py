# =============================================================================
# FILE: src/infrastructure/runtime_plane.py
# =============================================================================
# PURPOSE:
#   Generates Kubernetes Pod manifests for inference jobs.
#   Reads sandbox policy from Odoo and selects appropriate runtime class.
# =============================================================================

import os
import yaml
from typing import Dict, Any

class PodGenerator:
    def __init__(self, odoo_env=None):
        self.odoo_env = odoo_env  # Odoo environment for policy lookup

    def generate_pod_spec(self, job_id: str, user_id: int, code_source: str, requires_gpu: bool,
                          command: list, image: str, resources: Dict[str, str]) -> dict:
        """
        Generate a Pod manifest based on the active sandbox policy.
        """
        # Fetch policy from Odoo (simplified)
        policy = self.odoo_env['nettrades.sandbox.policy'].get_active_policy()
        runtime_class = policy.get_runtime_class(
            self.odoo_env['res.users'].browse(user_id),
            code_source,
            requires_gpu
        )

        # Map runtime class to Kubernetes value
        runtime_map = {
            'runc': None,  # default, no RuntimeClass needed
            'gvisor': 'gvisor',
            'gvisor_gpu': 'gvisor-gpu',
        }
        runtime_cls = runtime_map.get(runtime_class)

        manifest = {
            "apiVersion": "v1",
            "kind": "Pod",
            "metadata": {
                "name": f"job-{job_id}",
                "labels": {
                    "app": "nettrades-inference",
                    "job-id": job_id,
                }
            },
            "spec": {
                "containers": [{
                    "name": "worker",
                    "image": image,
                    "command": command,
                    "resources": {
                        "limits": resources,
                        "requests": resources,
                    },
                    "securityContext": {
                        "allowPrivilegeEscalation": False,
                        "readOnlyRootFilesystem": True,
                        "runAsNonRoot": True,
                    }
                }],
                "restartPolicy": "Never"
            }
        }

        if runtime_cls:
            manifest["spec"]["runtimeClassName"] = runtime_cls

        # Additional network/filesystem policies can be added via annotations or sidecars

        return manifest