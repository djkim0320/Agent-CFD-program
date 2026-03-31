import { useShell } from "../../store/ShellProvider";
import { canApprovePreflight, describeAiReviewState, describeDraftExecutionState, summarizeNormalizationSummary, summarizeRuntimeBlockerDetails } from "../../store/selectors";
import { EmptyState } from "../common/EmptyState";
import { StatusBadge } from "../common/StatusBadge";

function WarningList({ label, items, emptyText }: { label: string; items: string[]; emptyText: string }) {
  return (
    <div className="warning-block">
      <span>{label}</span>
      {items.length > 0 ? <ul>{items.map((item) => <li key={`${label}-${item}`}>{item}</li>)}</ul> : <p>{emptyText}</p>}
    </div>
  );
}

export function PreflightReviewBlock() {
  const { state, actions } = useShell();
  const preflight = state.draftPreflight;
  const canApprove = canApprovePreflight(preflight);
  const aiReviewState = describeAiReviewState(preflight);
  const executionState = describeDraftExecutionState(preflight);
  const normalizationRows = preflight ? summarizeNormalizationSummary(preflight.normalization_summary) : [];
  const blockerRows = summarizeRuntimeBlockerDetails(preflight);
  const isPreflightBusy = state.pending.preflight;
  const isApproveBusy = state.pending.approve;

  return (
    <section className="thread-block">
      <div className="thread-block__header">
        <div>
          <span className="thread-block__eyebrow">Preflight</span>
          <h2>Snapshot review</h2>
        </div>
        <div className="thread-block__actions">
          <button type="button" className="secondary-btn" onClick={() => void actions.runPreflight()} disabled={isPreflightBusy}>
            {isPreflightBusy ? "Analyzing..." : "Generate preflight"}
          </button>
          <button type="button" className="primary-btn" onClick={() => void actions.approveCurrentDraft()} disabled={isApproveBusy || !canApprove}>
            Approve &amp; run
          </button>
        </div>
      </div>

      {!preflight ? (
        <EmptyState
          title="No snapshot yet"
          body="Generate a preflight snapshot to review solver choice, blockers, hashes, and normalization details before creating a session."
        />
      ) : (
        <div className="thread-card">
          <div className="thread-card__meta">
            <StatusBadge label={executionState.label} tone={executionState.tone} />
            <StatusBadge label={aiReviewState.label} tone={aiReviewState.tone} />
            <StatusBadge label={preflight.mesh_strategy} />
          </div>
          <h3>{preflight.selected_solver} selected</h3>
          <p>{preflight.rationale}</p>
          <div className="summary-grid">
            <div>
              <span>Snapshot</span>
              <strong>{preflight.preflight_id}</strong>
            </div>
            <div>
              <span>Confidence</span>
              <strong>{Math.round(preflight.confidence * 100)}%</strong>
            </div>
            <div>
              <span>Runtime blockers</span>
              <strong>{preflight.runtime_blockers.length}</strong>
            </div>
            <div>
              <span>AI warnings</span>
              <strong>{preflight.ai_warnings.length}</strong>
            </div>
          </div>
          <div className="thread-card__warnings">
            <WarningList label="Runtime blockers" items={preflight.runtime_blockers} emptyText="No blockers detected." />
            <WarningList label="AI warnings" items={preflight.ai_warnings} emptyText="None reported." />
            <WarningList label="Policy warnings" items={preflight.policy_warnings} emptyText="None reported." />
          </div>
          {blockerRows.length > 0 ? (
            <div className="summary-detail-grid">
              {blockerRows.map((row) => (
                <div key={`${row.label}-${row.value}`} className="summary-detail-card">
                  <span>{row.label}</span>
                  <strong>{row.value}</strong>
                </div>
              ))}
            </div>
          ) : null}
          <div className="summary-detail-grid">
            {normalizationRows.length > 0 ? (
              normalizationRows.map((row) => (
                <div key={`${row.label}-${row.value}`} className="summary-detail-card">
                  <span>{row.label}</span>
                  <strong>{row.value}</strong>
                </div>
              ))
            ) : (
              <div className="summary-detail-card summary-detail-card--muted">
                <span>Normalization summary</span>
                <strong>Not published yet</strong>
              </div>
            )}
          </div>
        </div>
      )}
    </section>
  );
}
