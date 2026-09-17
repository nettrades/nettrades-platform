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
# The file res_partner.py adds a gpu_nodes One2many to res.partner. 
# That field is a reverse relation for gpu.node.partner_id. It would be useful in the UI (a "GPU Nodes" tab on the partner form), 
# but it's not required for any core functionality.
# The question is whether it causes a circular dependency. It doesn't — the class is a plain _inherit of res.partner, and res.partner is a core model
# But if you enable it, it may cause a conflict with nettrades_core (which might also extend res.partner), you'll see the AssertionError again

# from . import res_partner