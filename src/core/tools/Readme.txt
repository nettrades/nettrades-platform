src/core/tools/inference_tools.py
src/core/tools/odoo_tools.py

contains a shared Odoo-tool wrapper, an auto-detection layer that transparently picks the best inference backend (llama.cpp / vLLM / GPUStack), and a supervisor that routes incoming requests.