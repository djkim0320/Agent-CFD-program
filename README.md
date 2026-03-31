# Aero Agent Workspace

Independent local-first aerodynamic analysis agent for a Windows desktop workflow.

## Current workflow

- Upload geometry in the GUI shell
- Create a snapshot-backed preflight plan
- Require manual approval before execution
- Run approved jobs through the local worker, CFD core, solver adapters, and Docker SU2
- Publish SSE job events, a report, and artifacts back to the shell

## UI direction

- The GUI now runs as a desktop-first shell: sidebar + workspace thread + composer + inspector.
- The current vNext cleanup focuses on de-mock discipline, incremental stream updates, and clearer draft vs session lanes.
- The backend single-path flow stays intact while the shell becomes more thread-native and diagnostics stay in the inspector.

## Backend lifecycle notes

- Optional blank form fields are normalized server-side before preflight parsing.
- `create_job` is idempotent per preflight snapshot and returns an existing draft when present.
- Snapshot consumption is claimed at approval time, not by the worker.
- Job summaries expose source file name and timestamps for sidebar/session rows.
- STEP normalization failures are intended to surface as blocker-style preflight responses when the backend path supports it.
- AI advisory failures should surface as explicit unavailable/failed states; production UI paths should not treat provider fallback payloads as successful AI review.
- Frontend contract decoding is expected to stay strict: missing required fields should fail fast rather than being defaulted into `real` / `su2` / `remote`.
- Any provider fallback retained for local development must be explicit and opt-in, not a silent production behavior.
- User-facing GUI code does not keep a client-side mock helper path; any future fixtures belong in test/dev-only locations.

## Structure

- `apps/gui`: React + Vite frontend
- `services/local_api`: FastAPI local control plane
- `services/job_runner`: background execution service
- `packages/*`: contracts, runtime, providers, CFD core, adapters, viewer, installer
- `docs/PLANS.md`: implementation plan snapshot

## Development

- Install Python dependencies: `uv sync --group dev`
- Install frontend dependencies: `pnpm.cmd --dir apps/gui install`
- Start everything with one launcher: `run-aero-agent.bat`
- Start the API: `powershell -ExecutionPolicy Bypass -File scripts/start-api.ps1`
- Start the API from `cmd` or Explorer: `scripts\\start-api.bat`
- Start the GUI: `powershell -ExecutionPolicy Bypass -File scripts/start-gui.ps1`
- Start the GUI from `cmd` or Explorer: `scripts\\start-gui.bat`
- Start API + GUI together in separate windows: `scripts\\start-workbench.bat`
- Alternate combined launcher: `scripts\\start-app.bat`
- Run API tests: `powershell -ExecutionPolicy Bypass -File scripts/test-api.ps1`
- Run API tests from `cmd` or Explorer: `scripts\\test-api.bat`
- Build the GUI: `pnpm.cmd --dir apps/gui build`

## Provider notes

- `openai_api` is the primary direct API route.
- `codex_oauth` is modeled as a beta path on Windows and is WSL-preferred by product policy.
- The app does not read or manage raw Codex tokens directly.
