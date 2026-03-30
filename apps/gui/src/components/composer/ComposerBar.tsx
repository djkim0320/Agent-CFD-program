import { useShell } from "../../store/ShellProvider";

export function ComposerBar() {
  const { state, actions } = useShell();

  return (
    <div className="composer-bar">
      <div className="composer-bar__actions">
        <button type="button" className="chip-btn" onClick={() => void actions.runPreflight()}>
          Generate preflight
        </button>
        <button type="button" className="chip-btn" onClick={() => void actions.approveCurrentDraft()}>
          Approve this snapshot
        </button>
        <button type="button" className="chip-btn" onClick={() => actions.setInspectorTab("artifacts")}>
          Show artifacts
        </button>
        <button type="button" className="chip-btn" onClick={() => actions.setRoutePane("settings")}>
          Open settings
        </button>
      </div>

      <div className="composer-bar__editor">
        <textarea
          id="composer-input"
          rows={2}
          placeholder='Type a note or command like "generate preflight", "approve and run", or "show solver log".'
          value={state.composerText}
          onChange={(event) => actions.setComposerText(event.target.value)}
          onKeyDown={(event) => {
            if ((event.ctrlKey || event.metaKey) && event.key === "Enter") {
              event.preventDefault();
              void actions.submitComposer();
            }
          }}
        />
        <button type="button" className="primary-btn" onClick={() => void actions.submitComposer()}>
          Send
        </button>
      </div>

      <div className="composer-bar__hint">
        <span>Ctrl/Cmd+N: new analysis</span>
        <span>Ctrl/Cmd+K: focus composer</span>
        <span>Ctrl/Cmd+Enter: submit</span>
      </div>
    </div>
  );
}
