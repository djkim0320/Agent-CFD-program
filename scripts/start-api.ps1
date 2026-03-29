$paths = @(
  "services/local_api",
  "services/job_runner",
  "packages/contracts/src",
  "packages/common/src",
  "packages/agent_runtime/src",
  "packages/provider_openai/src",
  "packages/provider_codex/src",
  "packages/cfd_core/src",
  "packages/solver_adapters/src",
  "packages/viewer_assets/src",
  "packages/install_manager/src"
)

$env:PYTHONPATH = ($paths -join ";")
uv run uvicorn aero_agent_api.main:app --host 127.0.0.1 --port 8787 --reload
