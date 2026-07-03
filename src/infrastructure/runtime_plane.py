# =============================================================================
# FILE: src/infrastructure/runtime_plane.py
# =============================================================================
# PURPOSE:
#   Generates Kubernetes Pod manifests for inference jobs.
#   Reads sandbox policy from Odoo and selects appropriate runtime class.
#
# KEY FEATURES:
#   - Reads active sandbox policy from Odoo
#   - Selects runtime class based on user trust level, code source, and GPU requirements
#   - Generates Kubernetes Pod manifests with appropriate security contexts
#   - Supports gVisor with nvproxy for GPU-accelerated sandboxing
#   - Supports network egress and filesystem policies
#
# INTEGRATION POINTS:
#   - Odoo: Reads sandbox policy from nettrades.sandbox.policy model
#   - Kubernetes: Generates Pod manifests with RuntimeClass and annotations
#   - gVisor: Configures runsc with --nvproxy flag for GPU support
# =============================================================================

import os
import yaml
from typing import Dict, Any, Optional, List

class PodGenerator:
    """
    Generates Kubernetes Pod manifests for inference jobs.

    This class reads the active sandbox policy from Odoo and generates
    appropriate Pod manifests with the correct runtime class, security
    context, and resource limits.

    Attributes:
        odoo_env: Odoo environment for policy lookup.
    """

    def __init__(self, odoo_env=None):
        """
        Initialize the PodGenerator.

        Args:
            odoo_env: Odoo environment for policy lookup.
        """
        self.odoo_env = odoo_env

    def generate_pod_spec(
        self,
        job_id: str,
        user_id: int,
        code_source: str,
        requires_gpu: bool,
        command: list,
        image: str,
        resources: Dict[str, str],
        network_policy: Optional[str] = None,
        filesystem_policy: Optional[str] = None
    ) -> dict:
        """
        Generate a Pod manifest based on the active sandbox policy.

        This method:
        1. Fetches the active sandbox policy from Odoo
        2. Determines the appropriate runtime class based on user trust level,
           code source, and GPU requirements
        3. Generates a Kubernetes Pod manifest with the selected runtime class
           and security context

        Args:
            job_id: Unique identifier for the job.
            user_id: ID of the user submitting the job.
            code_source: Source of the code (e.g., 'downloaded', 'ai_generated',
                'internal_repo').
            requires_gpu: Whether the job requires GPU access.
            command: The command to run in the container.
            image: The container image to use.
            resources: Resource limits (cpu, memory, etc.).
            network_policy: Optional network egress policy override.
            filesystem_policy: Optional filesystem policy override.

        Returns:
            dict: Kubernetes Pod manifest.
        """
        # Fetch policy from Odoo
        if self.odoo_env:
            policy = self.odoo_env['nettrades.sandbox.policy'].get_active_policy()
            runtime_class = policy.get_runtime_class(
                self.odoo_env['res.users'].browse(user_id),
                code_source,
                requires_gpu
            )
            network_policy = network_policy or policy.network_egress
            filesystem_policy = filesystem_policy or policy.filesystem_policy
        else:
            # Fallback default policy if no Odoo environment is available
            runtime_class = 'gvisor_gpu' if requires_gpu else 'gvisor'
            network_policy = 'whitelist'
            filesystem_policy = 'workspace'

        # Map runtime class to Kubernetes RuntimeClass name
        runtime_map = {
            'runc': None,  # default, no RuntimeClass needed
            'gvisor': 'gvisor',
            'gvisor_gpu': 'gvisor-gpu',
        }
        runtime_cls = runtime_map.get(runtime_class)

        # Build the Pod manifest
        manifest = {
            "apiVersion": "v1",
            "kind": "Pod",
            "metadata": {
                "name": f"job-{job_id}",
                "labels": {
                    "app": "nettrades-inference",
                    "job-id": job_id,
                    "sandbox-policy": runtime_class,
                },
                "annotations": {
                    "nettrades.io/user-id": str(user_id),
                    "nettrades.io/code-source": code_source,
                    "nettrades.io/network-policy": network_policy,
                    "nettrades.io/filesystem-policy": filesystem_policy,
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
                        "capabilities": {
                            "drop": ["ALL"],
                        },
                    },
                    "volumeMounts": self._get_volume_mounts(filesystem_policy),
                }],
                "volumes": self._get_volumes(filesystem_policy),
                "restartPolicy": "Never",
            }
        }

        # Add RuntimeClass if needed
        if runtime_cls:
            manifest["spec"]["runtimeClassName"] = runtime_cls

        # Add network policy annotations for egress control
        if network_policy == 'blocked':
            manifest["metadata"]["annotations"]["k8s.ovn.org/pod-network"] = "deny-all"
        elif network_policy == 'whitelist':
            manifest["metadata"]["annotations"]["k8s.ovn.org/pod-network"] = "allow-whitelist"

        return manifest

    def _get_volume_mounts(self, filesystem_policy: str) -> List[Dict[str, str]]:
        """
        Get volume mounts based on the filesystem policy.

        Args:
            filesystem_policy: The filesystem policy ('readonly', 'workspace', 'full').

        Returns:
            List[Dict[str, str]]: List of volume mounts.
        """
        mounts = []

        if filesystem_policy == 'readonly':
            # Only allow read-only access to /tmp
            mounts.append({
                "name": "tmp",
                "mountPath": "/tmp",
                "readOnly": True,
            })
        elif filesystem_policy == 'workspace':
            # Allow read-write access to /workspace
            mounts.append({
                "name": "workspace",
                "mountPath": "/workspace",
                "readOnly": False,
            })
            mounts.append({
                "name": "tmp",
                "mountPath": "/tmp",
                "readOnly": True,
            })
        elif filesystem_policy == 'full':
            # Allow full access to /data
            mounts.append({
                "name": "data",
                "mountPath": "/data",
                "readOnly": False,
            })
            mounts.append({
                "name": "workspace",
                "mountPath": "/workspace",
                "readOnly": False,
            })
            mounts.append({
                "name": "tmp",
                "mountPath": "/tmp",
                "readOnly": False,
            })

        return mounts

    def _get_volumes(self, filesystem_policy: str) -> List[Dict[str, Any]]:
        """
        Get volumes based on the filesystem policy.

        Args:
            filesystem_policy: The filesystem policy ('readonly', 'workspace', 'full').

        Returns:
            List[Dict[str, Any]]: List of volumes.
        """
        volumes = []

        if filesystem_policy in ('readonly', 'workspace', 'full'):
            # Add emptyDir volumes for tmp and workspace
            volumes.append({
                "name": "tmp",
                "emptyDir": {
                    "sizeLimit": "1Gi",
                    "medium": "Memory",
                },
            })

        if filesystem_policy in ('workspace', 'full'):
            volumes.append({
                "name": "workspace",
                "emptyDir": {
                    "sizeLimit": "10Gi",
                },
            })

        if filesystem_policy == 'full':
            volumes.append({
                "name": "data",
                "emptyDir": {
                    "sizeLimit": "50Gi",
                },
            })

        return volumes

    def generate_confidential_gpu_manifest(
        self,
        job_id: str,
        model: str,
        prompt: str,
        requires_tee: bool = True
    ) -> dict:
        """
        Generate a secure Kubernetes Pod manifest for confidential GPU execution.

        This method enables NVIDIA Confidential Computing (CC) TEE linkage,
        which cryptographically links Intel TDX/AMD SEV CPU domains to the
        GPU's internal secure enclave, encrypting the PCIe data transit lanes.

        Args:
            job_id: Unique identifier for the job.
            model: The model to run (e.g., 'deepseek-r1:1.5b').
            prompt: The prompt to send to the model.
            requires_tee: Whether to enforce Trusted Execution Environment.

        Returns:
            dict: Kubernetes Pod manifest for confidential GPU execution.
        """
        manifest = {
            "apiVersion": "v1",
            "kind": "Pod",
            "metadata": {
                "name": f"confidential-vllm-{job_id}",
                "namespace": "secure-inference-pool",
                "labels": {
                    "app": "nettrades-inference",
                    "confidential-compute": "enabled",
                },
                "annotations": {
                    "nettrades.io/confidential-compute": str(requires_tee),
                }
            },
            "spec": {
                # Bypasses standard gVisor for high-throughput GPU virtualization
                # but forces a hardware-level Trusted Execution Environment (TEE)
                "runtimeClassName": "nvidia-confidential-compute" if requires_tee else "nvidia",
                "containers": [{
                    "name": "vllm-core-runner",
                    "image": "vllm/vllm-openai:latest",
                    "env": [
                        {"name": "NVIDIA_CONFIDENTIAL_COMPUTE", "value": "1" if requires_tee else "0"},
                        {"name": "MODEL_NAME", "value": model},
                        {"name": "PROMPT_DATA", "value": prompt},
                        {"name": "VLLM_API_KEY", "value": os.getenv("VLLM_API_KEY", "dummy")},
                    ],
                    "resources": {
                        "limits": {
                            "nvidia.com/gpu": "1",
                            "cpu": "4",
                            "memory": "16Gi",
                        },
                        "requests": {
                            "nvidia.com/gpu": "1",
                            "cpu": "2",
                            "memory": "8Gi",
                        },
                    },
                    "securityContext": {
                        "allowPrivilegeEscalation": False,
                        "readOnlyRootFilesystem": True,
                        "runAsNonRoot": True,
                    },
                    "ports": [{
                        "containerPort": 8000,
                        "name": "http",
                    }],
                }],
                "restartPolicy": "Never",
            }
        }

        return manifest