import { useEffect } from "react";
import { ComposerBar } from "../composer/ComposerBar";
import { NoticeBanner } from "../common/NoticeBanner";
import { InspectorDrawer } from "../inspector/InspectorDrawer";
import { Sidebar } from "../sidebar/Sidebar";
import { WorkspaceThread } from "../thread/WorkspaceThread";
import { useShell } from "../../store/ShellProvider";

export function AppShell() {
  const { state, actions } = useShell();

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "n") {
        event.preventDefault();
        actions.newAnalysis();
      }
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        const composer = document.getElementById("composer-input");
        if (composer instanceof HTMLTextAreaElement) {
          composer.focus();
        }
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [actions]);

  return (
    <div className="shell-layout">
      <Sidebar />
      <main className="shell-main">
        <header className="workspace-header">
          <div>
            <span className="workspace-header__eyebrow">Desktop workbench</span>
            <h2>Snapshot-aware CFD session shell</h2>
            <p>The backend execution path stays intact while preflight, approval, runtime, and artifacts are presented as a threaded desktop workflow.</p>
          </div>
        </header>
        {state.notice ? <NoticeBanner message={state.notice} onDismiss={actions.clearNotice} /> : null}
        <WorkspaceThread />
        <ComposerBar />
      </main>
      <InspectorDrawer />
    </div>
  );
}
