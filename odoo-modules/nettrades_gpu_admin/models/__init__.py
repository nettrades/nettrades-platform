# First, models that have no dependencies on other custom models

# Models that are referenced by others must come first
from . import gpu_cluster_subnet      # this must come before gpu_cluster
from . import gpu_cluster             # defines gpu.cluster
from . import gpu_node                # references gpu.cluster
from . import gpu_sharing_schedule    # references gpu.cluster
from . import gpu_token_economics     # references gpu.cluster (if any)
from . import multimodal_config       # simple config, no dependencies

# -----------------------------------------------------------------------------
# GPU Registration Token - secure token storage for node onboarding.
# This model implements SHA-256 hashed, one-time, expirable registration tokens.
# Without this import, the /api/v1/gpu/register endpoint will raise a
# "Model not found" error when trying to validate the token.
# -----------------------------------------------------------------------------
from . import gpu_registration_token