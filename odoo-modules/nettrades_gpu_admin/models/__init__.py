# -*- coding: utf-8 -*-
# =============================================================================
# GPU Admin Models
# =============================================================================

# Base model - MUST BE FIRST
from . import gpu_cluster

# Models that reference gpu.cluster
from . import gpu_cluster_subnet
from . import gpu_credit
from . import gpu_node
from . import gpu_pricing
from . import gpu_registration_token
from . import gpu_sharing_schedule
from . import gpu_token_economics

# Models with no dependencies
from . import multimodal_config

# res_partner is currently disabled to avoid circular dependency issues
# from . import res_partner