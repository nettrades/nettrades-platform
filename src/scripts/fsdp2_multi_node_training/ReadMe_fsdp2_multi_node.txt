This functiopnality is now automated via admin screen.
If you manually training within a company LAN (Trusted Mode)  use Axolotl with FSDP2 across the company's internal GPUs (same LAN, WireGuard mesh, sub-millisecond latency)

 Using Axolotl with FSDP2 across a company’s internal GPUs over a WireGuard mesh is a powerful and production-proven strategy. The key to making it work is a clean configuration and the correct NCCL environment variables to force traffic through the WireGuard interface.

Here is the concrete configuration and integration plan to make this work within your NETTRADES stack.
1. The Core Axolotl Configuration (FSDP2)

Multi-node training with Axolotl requires an identical copy of the software and configuration file on every machine participating in the training run. You must also ensure the main_process_ip (the master node) is reachable by all other nodes.

Since GPUs on a WireGuard mesh lack the high-speed interconnects found in a single server, QLoRA is essential. This technique allows you to fine-tune massive models (like a 70B parameter LLM) on consumer GPUs by drastically reducing memory pressure, making network communication the bottleneck rather than VRAM.

Below is the fsdp2_multi_node.yml file you’ll need to prepare on each node:
yaml

# Axolotl config: Multi-node FSDP2 + QLoRA
base_model: deepseek-ai/DeepSeek-R1-Distill-Qwen-14B
model_type: AutoModelForCausalLM
tokenizer_type: AutoTokenizer

# -- FSDP2 strategy --
fsdp_version: 2
fsdp_config:
  reshard_after_forward: true
  cpu_ram_efficient_loading: true
  state_dict_type: FULL_STATE_DICT
  offload_params: false

# -- QLoRA adapter --
adapter: qlora
lora_r: 16
lora_alpha: 32
lora_target_modules:
  - q_proj
  - k_proj
  - v_proj
  - o_proj

# -- Dataset & Training --
dataset: field_training_data
sequence_len: 2048
micro_batch_size: 2
gradient_accumulation_steps: 4
num_epochs: 3
learning_rate: 2e-4
bf16: true
# ... (wandb, logging, save paths)

This configuration is different from the single-node Unsloth one you saw earlier. You can't just use the same YAML file for multi-node training without specifying the FSDP version and config fields, as the requirements for sharding and state dict handling are completely different.
2. The Crucial Step: Configuring NCCL for WireGuard

This is the linchpin of the entire operation. By default, NCCL might try to use your standard Ethernet interface, which could route traffic outside the secure WireGuard mesh or fail to connect entirely. You must explicitly tell it to use the wg0 interface.

Set the following environment variables before launching the training run on each node:
bash

export NCCL_SOCKET_IFNAME=wg0
export NCCL_DEBUG=INFO
export NCCL_IB_DISABLE=1  # Disable InfiniBand, as we're using IP over WireGuard
export DDP_TIMEOUT=1800000  # 30 minutes
export WANDB_PROJECT=nettrades-finetune

The NCCL_SOCKET_IFNAME variable is the key instruction that tells the NCCL library to use the specified network interface (wg0) for all inter-GPU communication. Setting it bypasses any automatic interface selection and forces the traffic onto your encrypted mesh.
3. Launching the Distributed Training Job

With the configuration in place, launching the job follows the standard torchrun method. You'll need to run this command on every participating node.

First, define the environment variables used in the command:

    $MASTER_ADDR: The WireGuard IP of the master node (e.g., 10.100.0.1).

    $MASTER_PORT: An open port on the master node (e.g., 29400).

    $NNODES: The total number of nodes (machines) in this training run.

    $NPROC_PER_NODE: The number of GPUs on each node (e.g., 2).

Then, execute the following command simultaneously on your nodes:
bash

torchrun \
  --nnodes $NNODES \
  --nproc_per_node $NPROC_PER_NODE \
  --rdzv_id nettrades_finetune_job_001 \
  --rdzv_backend c10d \
  --rdzv_endpoint "$MASTER_ADDR:$MASTER_PORT" \
  -m axolotl.cli.train fsdp2_multi_node.yml

This is done via the CLI and is purpose-specific to your needs. The training will not begin until the specified number of nodes ($NNODES) and processes have connected to the master node.
4. Integrating Axolotl into the NETTRADES Automated Pipeline

Your NETTRADES system can automate this entire process, triggered by a "Good Answer" vote threshold being met.

    Odoo detects enough new votes and triggers a workflow for fine-tuning.

    NETTRADES LangGraph agent orchestrate a training job.

    The LangGraph agent decides where to run the training. Since this is a company executing the job, it will select its own Trusted GPU cluster.

    GPUStack, installed on the company's machines, receives the job from LangGraph. It pulls the fsdp2_multi_node.yml config file and sets the NCCL environment variables.

    GPUStack launches the torchrun command on all the selected internal company nodes. It passes the node count and the WireGuard IP of the master node.

    Once training is complete, GPUStack reports back success. The agent then registers the new fine-tuned model in Odoo (as a new llm.provider), completing the self-learning loop.

Axolotl's latest release (v0.16.1) also includes experimental support for Group Relative Policy Optimization (GRPO) via FSDP2, which could be used for more advanced preference-based training in the future.

