# First, models that have no dependencies on other custom models

# Models that are referenced by others must come first.
# gpu.cluster is the base model; all other GPU models depend on it.
from . import gpu_cluster             # defines gpu.cluster – MUST BE FIRST

# Now models that reference gpu.cluster
from . import gpu_cluster_subnet      # references gpu.cluster via cluster_id
from . import gpu_node                # references gpu.cluster
from . import gpu_sharing_schedule    # references gpu.cluster
from . import gpu_token_economics     # references gpu.cluster (if any)

# Models with no dependencies (can be anywhere)
from . import multimodal_config       # simple config, no dependencies

# New model (2026-06-28) – no dependency on gpu.cluster, safe at the end
from . import gpu_registration_token