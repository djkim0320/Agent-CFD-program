import { useShell } from "../../store/ShellProvider";
import { selectDraftNotes } from "../../store/selectors";
import { EmptyState } from "../common/EmptyState";
import { StatusBadge } from "../common/StatusBadge";

export function DraftWorkspaceView() {
  const { state, actions } = useShell();
  const draftNotes = selectDraftNotes(state);
  const hasPreflight = Boolean(state.draftPreflight);
  const solverPreference = state.draft.solverPreference === "su2" ? "su2" : "auto";

  return (
    <section className="thread-block">
      <div className="thread-block__header">
        <div>
          <span className="thread-block__eyebrow">Draft workspace</span>
          <h2>Prepare the next analysis</h2>
        </div>
        <StatusBadge label={hasPreflight ? "snapshot ready" : "draft only"} tone={hasPreflight ? "good" : "neutral"} />
      </div>

      <div className="draft-grid">
        <label className="upload-card">
          <span>Geometry file</span>
          <input
            type="file"
            accept=".step,.stp,.stl,.obj"
            onChange={(event) => actions.setDraftField("geometryFile", event.target.files?.[0] ?? null)}
          />
          <strong>{state.draft.geometryFile?.name ?? "Choose a geometry file"}</strong>
          <small>STL/OBJ are the primary real-path inputs. STEP remains conditional on tessellation success.</small>
        </label>

        <div className="detail-card">
          <span>Conditions</span>
          <div className="form-grid">
            <label>
              <span>Unit</span>
              <select value={state.draft.unit} onChange={(event) => actions.setDraftField("unit", event.target.value)}>
                <option value="m">m</option>
                <option value="cm">cm</option>
                <option value="mm">mm</option>
                <option value="in">in</option>
                <option value="ft">ft</option>
              </select>
            </label>
            <label>
              <span>Fidelity</span>
              <select value={state.draft.fidelity} onChange={(event) => actions.setDraftField("fidelity", event.target.value)}>
                <option value="fast">fast</option>
                <option value="balanced">balanced</option>
                <option value="high">high</option>
              </select>
            </label>
            <label>
              <span>Solver preference</span>
              <select value={solverPreference} onChange={(event) => actions.setDraftField("solverPreference", event.target.value)}>
                <option value="auto">auto</option>
                <option value="su2">su2</option>
              </select>
              <small>Other solver paths remain deferred in this shell.</small>
            </label>
            <label>
              <span>Forward / Up</span>
              <div className="axis-pair">
                <select value={state.draft.frame.forwardAxis} onChange={(event) => actions.setDraftSection("frame", { forwardAxis: event.target.value })}>
                  <option value="x">x</option>
                  <option value="y">y</option>
                  <option value="z">z</option>
                </select>
                <select value={state.draft.frame.upAxis} onChange={(event) => actions.setDraftSection("frame", { upAxis: event.target.value })}>
                  <option value="x">x</option>
                  <option value="y">y</option>
                  <option value="z">z</option>
                </select>
              </div>
            </label>
            <label>
              <span>AoA</span>
              <input value={state.draft.flow.aoa} onChange={(event) => actions.setDraftSection("flow", { aoa: event.target.value })} />
            </label>
            <label>
              <span>Sideslip</span>
              <input value={state.draft.flow.sideslip} onChange={(event) => actions.setDraftSection("flow", { sideslip: event.target.value })} />
            </label>
            <label>
              <span>Velocity</span>
              <input value={state.draft.flow.velocity} onChange={(event) => actions.setDraftSection("flow", { velocity: event.target.value })} />
            </label>
            <label>
              <span>Mach</span>
              <input value={state.draft.flow.mach} onChange={(event) => actions.setDraftSection("flow", { mach: event.target.value })} />
            </label>
            <label>
              <span>Area</span>
              <input value={state.draft.referenceValues.area} onChange={(event) => actions.setDraftSection("referenceValues", { area: event.target.value })} />
            </label>
            <label>
              <span>Length</span>
              <input value={state.draft.referenceValues.length} onChange={(event) => actions.setDraftSection("referenceValues", { length: event.target.value })} />
            </label>
            <label>
              <span>Span</span>
              <input value={state.draft.referenceValues.span} onChange={(event) => actions.setDraftSection("referenceValues", { span: event.target.value })} />
            </label>
            <label className="form-grid__notes">
              <span>Notes</span>
              <textarea value={state.draft.notes} rows={4} onChange={(event) => actions.setDraftField("notes", event.target.value)} />
            </label>
          </div>
        </div>
      </div>

      {draftNotes.length > 0 ? (
        <div className="note-stack">
          {draftNotes.map((note) => (
            <article key={note.id} className="note-card">
              <span>Composer note</span>
              <p>{note.text}</p>
            </article>
          ))}
        </div>
      ) : (
        <EmptyState title="No draft notes yet" body="Use the composer to capture notes that belong to this draft." />
      )}
    </section>
  );
}
