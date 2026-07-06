# -*- coding: utf-8 -*-
# =============================================================================
# GPU Admin Models
# =============================================================================

# Base model - MUST BE FIRST
from . import gpu_cluster

# Models that reference gpu.cluster
from . import gpu_cluster_subnet
from . import gpu_node
from . import gpu_sharing_schedule
from . import gpu_token_economics

# Models with no dependencies
from . import multimodal_config

# New model (2026-06-28)
from . import gpu_registration_token

# res_partner is currently disabled to avoid circular dependency issues
# from . import res_partner