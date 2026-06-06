vllm-deployment.yaml file now serves as a self-contained reference; any future operator can read it and know exactly when and how to enable GPU inference on Kubernetes.


The apps/ai/vllm-deployment.yaml file is commented out intentionally—it is a safety default, not a missing feature. Here is the reasoning, how the auto-detection works, and exactly what you need to do to enable GPU inference on Kubernetes.
Why the vLLM manifest is commented out by default

    It is optional hardware. Not every Kubernetes cluster has NVIDIA GPU nodes. If we applied the file unconditionally, the vLLM pod would sit in Pending state forever because no node could satisfy the nvidia.com/gpu.present=true label. This would generate error events and confusion for new operators.

    The auto-detection already picks the best backend at runtime. The LangGraph agent (in nettrades-app) does not need vLLM to be present. It checks environment variables in this order:

        GPUSTACK_SERVER_URL → use GPUStack

        VLLM_BASE_URL → use vLLM

        LLM_BASE_URL → use llama.cpp (fallback)

    On a Kubernetes deployment, we set GPUSTACK_SERVER_URL in the LangGraph pod, so inference goes through GPUStack automatically. vLLM becomes an optional, additional backend that GPUStack itself can manage—or you can bypass GPUStack entirely and use vLLM directly on a dedicated GPU node.

    Keeping it commented out makes the default deployment work out-of-the-box on any Talos cluster, whether it has GPUs or not. The operator only uncomments it when they have provisioned GPU worker nodes.

When to uncomment and enable vLLM

You should enable the vLLM deployment only when:

    You have at least one Kubernetes worker node with a supported NVIDIA GPU.

    You have installed the NVIDIA GPU Operator (version v26.3.1 or later) on the cluster.

    You have labelled the GPU node(s) with nvidia.com/gpu.present=true.

    You want to bypass GPUStack for inference on that specific GPU (e.g., for a dedicated high-performance inference node).

Step-by-step to activate vLLM on a Kubernetes node

    Label the GPU node:
    bash

    kubectl label node <gpu-node-name> nvidia.com/gpu.present=true

    Create the required secret (if you want API-key authentication):
    bash

    kubectl create secret generic vllm-secret \
        --namespace ai \
        --from-literal=api-key=$(openssl rand -base64 32)

    Uncomment the entire vllm-deployment.yaml file (remove the leading # from every line). You can do this by removing the block comment markers and re-applying.

    Add the file to the AI kustomization – in apps/ai/kustomization.yaml, uncomment the line:
    yaml

    # - vllm-deployment.yaml

    Set the environment variable in the LangGraph deployment (apps/ai/langgraph-deployment.yaml) to point to the vLLM service instead of GPUStack, if you want to use vLLM directly:
    yaml

    - name: VLLM_BASE_URL
      value: http://vllm.ai.svc.cluster.local:8000/v1

    (Leave GPUSTACK_SERVER_URL empty or remove it.)

    Apply the changes:
    bash

    kubectl apply -k apps/ai/

Now the LangGraph agent will auto-detect VLLM_BASE_URL and use the vLLM service for inference.
Summary

The file is commented out so the platform starts without requiring a GPU. The auto-detection code already handles multiple backends; you only need to uncomment and configure the vLLM manifest when you deliberately want to add dedicated GPU inference nodes to your Kubernetes cluster. This design keeps the default deployment lightweight and avoids unnecessary failures.