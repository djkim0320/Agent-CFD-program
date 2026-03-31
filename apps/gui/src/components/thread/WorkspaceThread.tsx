import { useShell } from "../../store/ShellProvider";
import { DraftWorkspaceView } from "./DraftWorkspaceView";
import { PreflightReviewBlock } from "./PreflightReviewBlock";
import { SessionActivityThread } from "./SessionActivityThread";
import { SessionResultSummary } from "./SessionResultSummary";

export function WorkspaceThread() {
  const { state } = useShell();

  const showingSession = Boolean(state.selectedJobId);

  return (
    <div className="workspace-thread">
      {showingSession ? (
        <>
          <SessionActivityThread />
          <SessionResultSummary />
        </>
      ) : (
        <>
          <DraftWorkspaceView />
          <PreflightReviewBlock />
        </>
      )}
    </div>
  );
}
