# 아키텍처 개요

## Runtime Layers

1. `apps/gui`
   - 로컬 브라우저 GUI
   - 업로드, 조건 입력, preflight review, 실행 스트림, 결과/이력
2. `services/local_api`
   - loopback HTTP API
   - SQLite metadata, SSE event stream, artifact serving
3. `packages/agent_runtime`
   - job lifecycle orchestration
   - subagent fan-out, provider routing, approval gating
4. `packages/cfd_core`
   - geometry ingest, solver selection, case preparation, postprocess
5. `packages/solver_adapters`
   - SU2/OpenFOAM/VSPAERO runner adapters
6. `packages/provider_*`
   - `provider_openai`: OpenAI API adapter
   - `provider_codex`: Codex SDK -> app-server(exp) -> noninteractive -> MCP fallback

## Boundaries

- GUI/API: loopback only
- solver execution: out-of-process
- provider execution: adapter boundary
- job artifacts: local file system only

## Vertical Slice Goal

v0 scaffold는 다음을 실제로 연결하는 것을 목표로 한다.

1. geometry 업로드
2. preflight 생성
3. user approval
4. background run state transition
5. report/viewer asset 노출
