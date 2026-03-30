export function StatusBadge({
  label,
  tone = "neutral",
}: {
  label: string;
  tone?: "neutral" | "good" | "warning" | "danger";
}) {
  return <span className={`status-badge status-badge--${tone}`}>{label}</span>;
}
