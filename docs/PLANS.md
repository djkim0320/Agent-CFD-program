# Plan Snapshot

## Current direction

- Keep the existing backend single-path CFD flow intact.
- Rework the GUI into a desktop-first app shell and conversational workbench.
- Keep the local-first, snapshot-backed execution model.

## Lifecycle correctness focus

- Optional blank form fields should normalize to `None` before preflight parsing.
- `create_job` should be idempotent per preflight snapshot.
- Snapshot consumption should happen atomically at approval time, not in the worker.
- Job summary responses should include source file name and timestamps for session rows.
- STEP normalization failures should be treated as user-facing blocker cases instead of generic server errors when the backend path supports it.

## Current implementation status

- Backend preflight / approval / worker separation is already in place.
- Snapshot-backed execution and SSE events are already the active path.
- GUI shell refactor is still the next major UX layer.

## Next UI layer

- Sidebar for recent sessions and settings.
- Threaded workspace for preflight, approval, run, and artifact events.
- Composer bar for quick actions.
- Inspector drawer for hashes, blockers, and artifact metadata.
