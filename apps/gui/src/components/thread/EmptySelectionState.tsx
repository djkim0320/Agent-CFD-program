import { EmptyState } from "../common/EmptyState";

export function EmptySelectionState({
  title = "No session selected",
  body = "Choose a recent session from the sidebar or approve the current snapshot to create one.",
}: {
  title?: string;
  body?: string;
}) {
  return <EmptyState title={title} body={body} />;
}
