export function NoticeBanner({
  message,
  onDismiss,
}: {
  message: string;
  onDismiss?: () => void;
}) {
  return (
    <div className="notice-banner">
      <div>
        <span className="notice-banner__eyebrow">Notice</span>
        <p>{message}</p>
      </div>
      {onDismiss ? (
        <button className="notice-banner__dismiss" type="button" onClick={onDismiss}>
          Dismiss
        </button>
      ) : null}
    </div>
  );
}
