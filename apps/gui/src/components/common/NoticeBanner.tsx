import type { DiagnosticIssue } from "../../lib/types";

export function NoticeBanner({
  issue,
  onDismiss,
}: {
  issue: DiagnosticIssue;
  onDismiss?: () => void;
}) {
  return (
    <div className="notice-banner">
      <div>
        <span className="notice-banner__eyebrow">{issue.severity}</span>
        <p>
          <strong>{issue.title}</strong> {issue.detail}
        </p>
        {issue.nextAction ? <p>{issue.nextAction}</p> : null}
      </div>
      {onDismiss ? (
        <button className="notice-banner__dismiss" type="button" onClick={onDismiss}>
          Dismiss
        </button>
      ) : null}
    </div>
  );
}
