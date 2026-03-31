import { useShell } from "../../store/ShellProvider";

export function ComposerBar() {
  const { state, actions } = useShell();
  const trimmed = state.composerText.trim();
  const isCommand = trimmed.startsWith("/");
  const isBusy = state.pending.composer || state.pending.preflight || state.pending.approve || state.pending.refresh || state.pending.cancel;

  return (
    <div className="composer-bar">
      <div className="composer-bar__actions">
        <button type="button" className="chip-btn" onClick={() => void actions.runPreflight()} disabled={isBusy}>
          Generate preflight
        </button>
        <button type="button" className="chip-btn" onClick={() => void actions.approveCurrentDraft()} disabled={isBusy}>
          Approve this snapshot
        </button>
        <button type="button" className="chip-btn" onClick={() => actions.setInspectorTab("diagnostics")}>
          Open diagnostics
        </button>
        <button type="button" className="chip-btn" onClick={() => void actions.refreshSelectedJob()} disabled={isBusy || !state.selectedJobId}>
          Refresh selected session
        </button>
      </div>

      <div className="composer-bar__editor">
        <textarea
          id="composer-input"
          rows={2}
          placeholder="Write a note, or run /preflight, /approve, /refresh, /diagnostics, or /log."
          value={state.composerText}
          onChange={(event) => actions.setComposerText(event.target.value)}
          onKeyDown={(event) => {
            if ((event.ctrlKey || event.metaKey) && event.key === "Enter") {
              event.preventDefault();
              void actions.submitComposer();
            }
          }}
        />
        <button type="button" className="primary-btn" onClick={() => void actions.submitComposer()} disabled={isBusy || !trimmed}>
          {isBusy ? "Working..." : isCommand ? "Run command" : "Add note"}
        </button>
      </div>

      <div className="composer-bar__hint">
        <span>Ctrl/Cmd+N: new analysis</span>
        <span>Ctrl/Cmd+K: focus composer</span>
        <span>Slash commands only run when the input starts with `/`</span>
        <span>Ctrl/Cmd+Enter: submit</span>
      </div>
    </div>
  );
}
