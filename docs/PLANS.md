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
- Provider availability should surface as explicit `unavailable` / `failed` advisory states, not as user-facing success through local fallback payloads.
- GUI/API boundary decoding should remain strict for required fields; missing values should fail fast instead of being coerced into `real`, `su2`, or `remote`.
- Any retained fallback for local development must be explicit and opt-in only.

## Current implementation status

- Backend preflight / approval / worker separation is already in place.
- Snapshot-backed execution and SSE events are already the active path.
- GUI shell is already active as `sidebar + workspace thread + composer + inspector`.
- The next cleanup layer is de-mock discipline, stream refetch reduction, and clearer draft-vs-session separation.

## Current cleanup focus

- Keep the backend single-path flow intact.
- Make the workspace more thread-native and stop mixing draft/session lanes.
- Prefer incremental stream merge over hot-event refetches.
- Keep raw payloads and decode issues inside inspector diagnostics, not in the main lane.
