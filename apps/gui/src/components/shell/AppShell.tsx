import { useEffect } from "react";
import { ComposerBar } from "../composer/ComposerBar";
import { NoticeBanner } from "../common/NoticeBanner";
import { InspectorDrawer } from "../inspector/InspectorDrawer";
import { Sidebar } from "../sidebar/Sidebar";
import { getPrimaryDiagnosticIssue } from "../../store/selectors";
import { ReportsView } from "../thread/ReportsView";
import { SettingsView } from "../thread/SettingsView";
import { WorkspaceThread } from "../thread/WorkspaceThread";
import { useShell } from "../../store/ShellProvider";

export function AppShell() {
  const { state, actions } = useShell();
  const primaryIssue = getPrimaryDiagnosticIssue(state);

  const headerCopy =
    state.routePane === "reports"
      ? {
          eyebrow: "Report library",
          title: "Generated session outputs",
          detail: "Completed sessions with published summaries and reports live here. Select one to jump back into the workspace thread.",
        }
      : state.routePane === "settings"
        ? {
            eyebrow: "Settings",
            title: "Provider and runtime controls",
            detail: "Connection readiness, runtime checks, and shell-level environment details stay in this pane instead of competing with the workspace thread.",
          }
        : {
            eyebrow: "Desktop workbench",
            title: "Snapshot-aware CFD session shell",
            detail:
              "Draft preparation, preflight review, and persistent session activity stay separated so the main lane reads like a work log instead of a dashboard stack.",
          };

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
            <span className="workspace-header__eyebrow">{headerCopy.eyebrow}</span>
            <h2>{headerCopy.title}</h2>
            <p>{headerCopy.detail}</p>
          </div>
        </header>
        {primaryIssue ? <NoticeBanner issue={primaryIssue} onDismiss={actions.clearNotice} /> : null}
        {state.routePane === "reports" ? <ReportsView /> : null}
        {state.routePane === "settings" ? <SettingsView /> : null}
        {state.routePane === "workspace" ? <WorkspaceThread /> : null}
        <ComposerBar />
      </main>
      <InspectorDrawer />
    </div>
  );
}
