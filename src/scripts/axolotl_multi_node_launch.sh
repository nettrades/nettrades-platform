#!/bin/bash
# =============================================================================
# Axolotl Multi-Node Training Launcher (WireGuard mesh)
# =============================================================================
# Sets NCCL to use the WireGuard interface and launches torchrun.
# All environment variables have sensible defaults.
# =============================================================================
set -euo pipefail

export NCCL_SOCKET_IFNAME=wg0
export NCCL_DEBUG=INFO
export NCCL_IB_DISABLE=1
export DDP_TIMEOUT=1800000

# Set defaults if not provided by GPUStack/Odoo
MASTER_ADDR=${MASTER_ADDR:-10.100.0.1}
MASTER_PORT=${MASTER_PORT:-29400}
NNODES=${NNODES:-2}
NPROC_PER_NODE=${NPROC_PER_NODE:-2}

echo "Starting Axolotl FSDP2 training: $NNODES nodes, $NPROC_PER_NODE GPUs per node."
echo "Master: $MASTER_ADDR:$MASTER_PORT   Mesh interface: wg0"

torchrun \
  --nnodes "$NNODES" \
  --nproc_per_node "$NPROC_PER_NODE" \
  --rdzv_id nettrades_finetune \
  --rdzv_backend c10d \
  --rdzv_endpoint "$MASTER_ADDR:$MASTER_PORT" \
  -m axolotl.cli.train fsdp2_multi_node.yml