import { useShell } from "../../store/ShellProvider";
import { describeProviderState, describeRuntimeState } from "../../store/selectors";
import { StatusBadge } from "../common/StatusBadge";

export function SettingsView() {
  const { state, actions } = useShell();
  const providerState = describeProviderState(state.connectionStatus);
  const runtimeState = describeRuntimeState(state.installStatus);

  return (
    <div className="thread-block">
      <div className="thread-block__header">
        <div>
          <span className="thread-block__eyebrow">Settings</span>
          <h2>Provider and runtime status</h2>
        </div>
      </div>
      <div className="thread-block__actions">
        <button
          type="button"
          className={state.connectionMode === "openai_api" ? "primary-btn" : "secondary-btn"}
          onClick={() => actions.setConnectionMode("openai_api")}
        >
          openai_api
        </button>
        <button
          type="button"
          className={state.connectionMode === "codex_oauth" ? "primary-btn" : "secondary-btn"}
          onClick={() => actions.setConnectionMode("codex_oauth")}
        >
          codex_oauth
        </button>
      </div>
      <div className="settings-grid">
        <div className="detail-card">
          <span>Connection mode</span>
          <strong>{state.connectionMode}</strong>
          <StatusBadge label={providerState.label} tone={providerState.tone} />
          <p>{providerState.detail}</p>
        </div>
        <div className="detail-card">
          <span>Runtime readiness</span>
          <strong>{runtimeState.label}</strong>
          <StatusBadge label={runtimeState.label} tone={runtimeState.tone} />
          <p>{runtimeState.detail}</p>
        </div>
      </div>
    </div>
  );
}
