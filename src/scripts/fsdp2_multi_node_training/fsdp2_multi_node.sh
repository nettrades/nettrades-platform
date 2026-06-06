export NCCL_SOCKET_IFNAME=wg0
export NCCL_DEBUG=INFO
export NCCL_IB_DISABLE=1  # Disable InfiniBand, as we're using IP over WireGuard
export DDP_TIMEOUT=1800000  # 30 minutes
export WANDB_PROJECT=nettrades-finetune