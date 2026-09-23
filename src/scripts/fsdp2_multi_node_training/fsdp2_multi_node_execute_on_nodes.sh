# FILE: src/scripts/fsdp2_multi_node_training/fsdp2_multi_node_execute_on_nodes.sh
torchrun \
  --nnodes $NNODES \
  --nproc_per_node $NPROC_PER_NODE \
  --rdzv_id nettrades_finetune_job_001 \
  --rdzv_backend c10d \
  --rdzv_endpoint "$MASTER_ADDR:$MASTER_PORT" \
  -m axolotl.cli.train fsdp2_multi_node.yml