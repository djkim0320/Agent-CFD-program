# Aero Agent Workspace

Independent local-first aerodynamic analysis agent scaffold for a Windows-installed, browser-based desktop workflow.

## Current vertical slice

- Upload `STEP/STL/OBJ/.vsp3` geometry through the GUI scaffold
- Generate a preflight solver plan
- Require manual approval before mutable execution
- Run a deterministic mock CFD pipeline to completion
- Publish SSE job events, a HTML report placeholder, and viewer assets

## Structure

- `apps/gui`: React + Vite frontend
- `services/local_api`: FastAPI local control plane
- `services/job_runner`: background execution service
- `packages/*`: contracts, runtime, providers, CFD core, adapters, viewer, installer
- `docs/PLANS.md`: implementation plan snapshot

## Development

- Install Python dependencies: `uv sync --group dev`
- Install frontend dependencies: `pnpm.cmd --dir apps/gui install`
- Start the API: `powershell -ExecutionPolicy Bypass -File scripts/start-api.ps1`
- Start the GUI: `powershell -ExecutionPolicy Bypass -File scripts/start-gui.ps1`
- Run API tests: `powershell -ExecutionPolicy Bypass -File scripts/test-api.ps1`
- Build the GUI: `pnpm.cmd --dir apps/gui build`

## Provider notes

- `openai_api` is the primary direct API route.
- `codex_oauth` is modeled as a beta path on Windows and is WSL-preferred by product policy.
- The app does not read or manage raw Codex tokens directly.
