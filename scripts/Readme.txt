The orchestrator and phase scripts now include pre-flight checks at every entry point. The scripts are fully idempotent — you can re-run them safely. The design rule is simple:

    Phase 2 needs a Phase 1 environment — if it is missing, run Phase 1 first.

    Phase 3 needs a working Phase 2 deployment — if it is missing, run Phase 2 first.

    Phase 4 needs an nettrades-infra project — if it is missing, tell the operator exactly what to do.

Summary of Safeguards
Scenario	What the scripts do
Run Phase 2 before Phase 1	Phase 2 detects missing repos and auto-runs Phase 1
Run Phase 3 before Phase 2	Phase 3 detects missing .env and auto-runs Phase 2 (which auto-runs Phase 1 if needed)
Run Phase 4 before Phase 2	Phase 4 does not auto-run Phase 2 — Kubernetes is a separate deployment path. But it checks all required tools and provides installation links
Re-run any phase	All phases are idempotent — git clone checks for existing .git folders; pip install checks for existing packages; Docker Compose and tofu apply are both safe to re-run
GPU not present when running Phase 3	Phase 3 checks nvidia-smi and exits with a clear error message
Missing Kubernetes tools	Phase 4 lists each missing tool with an installation URL
Missing terraform.tfvars	Phase 4 prints the exact copy command needed

The operator can safely re-run any phase at any time, and the scripts will detect missing prerequisites, install them automatically where possible, and provide clear instructions where manual intervention is required.


text

┌─────────────────────────────────────────────────────────────┐
│  nettrades setup                       ← ONE command        │
│  (interactive wizard, calls everything below)               │
├─────────────────────────────────────────────────────────────┤
│  Phase 1 — dev-env                     │  Phase 2 — deploy   │
│  • Clones repos                        │  • Generates secrets│
│  • Installs dependencies               │  • Builds images    │
│  • Creates folder structure            │  • Starts Docker    │
│  • Writes config files                 │  • Initialises DB  │
│                                        │  • Schedules backups│
├────────────────────────────────────────┼────────────────────┤
│  Phase 3 — add-gpu                     │  Phase 4 — scale   │
│  • Detects NVIDIA GPU                  │  • Validates K8s   │
│  • Installs container toolkit          │  • Deploys Talos   │
│  • Migrates llama.cpp → vLLM           │  • Applies manifests│
│  • Enables GPUStack workers            │  • Configures Argo │
└────────────────────────────────────────┴────────────────────┘