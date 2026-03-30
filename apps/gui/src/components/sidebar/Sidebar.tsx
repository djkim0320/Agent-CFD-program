import { useMemo } from "react";
import { useShell } from "../../store/ShellProvider";
import { describeProviderState, describeRuntimeState, formatTimestamp, getOverallState, getSidebarSessions } from "../../store/selectors";
import { StatusBadge } from "../common/StatusBadge";

function toneForSessionStatus(status: string): "neutral" | "good" | "warning" | "danger" {
  if (status === "completed") return "good";
  if (status === "failed" || status === "cancelled") return "danger";
  if (status === "running" || status === "queued" || status === "postprocessing") return "warning";
  return "neutral";
}

export function Sidebar() {
  const { state, actions } = useShell();
  const sessions = useMemo(() => getSidebarSessions(state), [state]);
  const draftState = getOverallState(state.draftPreflight);
  const providerState = describeProviderState(state.connectionStatus);
  const runtimeState = describeRuntimeState(state.installStatus);

  return (
    <aside className="shell-sidebar">
      <div className="shell-brand">
        <div className="shell-brand__mark">AA</div>
        <div>
          <h1>Aero Agent</h1>
          <p>Local CFD workbench</p>
        </div>
      </div>

      <button className="shell-sidebar__primary" type="button" onClick={actions.newAnalysis}>
        New Analysis
      </button>

      <div className="shell-sidebar__nav">
        <button type="button" className={state.routePane === "workspace" ? "is-active" : ""} onClick={() => actions.setRoutePane("workspace")}>
          Workspace
        </button>
        <button type="button" className={state.routePane === "reports" ? "is-active" : ""} onClick={() => actions.setRoutePane("reports")}>
          Reports
        </button>
        <button type="button" className={state.routePane === "settings" ? "is-active" : ""} onClick={() => actions.setRoutePane("settings")}>
          Settings
        </button>
      </div>

      <section className="sidebar-panel">
        <div className="sidebar-panel__header">
          <span>Current Draft</span>
          <StatusBadge label={draftState} tone={draftState === "real" ? "good" : draftState === "blocked" ? "danger" : "neutral"} />
        </div>
        <strong>{state.draft.geometryFile?.name ?? "No geometry selected"}</strong>
        <p>
          {state.draftPreflight
            ? `${state.draftPreflight.selected_solver} / ${state.draftPreflight.execution_mode}`
            : "Draft remains provisional until a preflight snapshot is generated."}
        </p>
      </section>

      <section className="sidebar-panel">
        <div className="sidebar-panel__header">
          <span>Recent Sessions</span>
          <small>{sessions.length}</small>
        </div>
        <div className="session-list">
          {sessions.length === 0 ? (
            <p className="sidebar-muted">Persistent sessions appear after you create a job from a snapshot.</p>
          ) : (
            sessions.map((job) => (
              <button
                key={job.id}
                type="button"
                className={state.selectedJobId === job.id ? "session-row is-active" : "session-row"}
                onClick={() => actions.selectJob(job.id)}
              >
                <div className="session-row__top">
                  <strong>{job.source_file_name}</strong>
                  <StatusBadge label={job.status} tone={toneForSessionStatus(job.status)} />
                </div>
                <div className="session-row__meta">
                  <span>{job.selected_solver}</span>
                  <span>{formatTimestamp(job.updated_at)}</span>
                </div>
                {job.error ? <span className="session-row__error">{job.error}</span> : null}
              </button>
            ))
          )}
        </div>
      </section>

      <section className="sidebar-panel">
        <div className="sidebar-panel__header">
          <span>Environment</span>
        </div>
        <div className="sidebar-kv">
          <span>Provider</span>
          <strong>{providerState.label}</strong>
          <span>Runtime</span>
          <strong>{runtimeState.label}</strong>
        </div>
        <p>{providerState.detail}</p>
        <p>{runtimeState.detail}</p>
      </section>
    </aside>
  );
}
