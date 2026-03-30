import { useEffect, type Dispatch } from "react";
import type { RoutePane, ShellAction, InspectorTab } from "./shellTypes";

interface UseRouteSyncArgs {
  routePane: RoutePane;
  selectedJobId: string | null;
  selectedInspectorTab: InspectorTab;
  dispatch: Dispatch<ShellAction>;
}

function readRouteFromLocation() {
  const params = new URLSearchParams(window.location.search);
  const pane = params.get("pane");
  const jobId = params.get("job");
  const inspector = params.get("inspector");
  return {
    pane: pane === "reports" || pane === "settings" ? pane : "workspace",
    jobId,
    inspector: inspector === "run" || inspector === "artifacts" || inspector === "environment" || inspector === "diagnostics" ? inspector : "snapshot",
  } as const;
}

export function useRouteSync({ routePane, selectedJobId, selectedInspectorTab, dispatch }: UseRouteSyncArgs) {
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    params.set("pane", routePane);
    if (selectedJobId) {
      params.set("job", selectedJobId);
    } else {
      params.delete("job");
    }
    params.set("inspector", selectedInspectorTab);
    const query = params.toString();
    window.history.replaceState(null, "", `${window.location.pathname}${query ? `?${query}` : ""}`);
  }, [routePane, selectedInspectorTab, selectedJobId]);

  useEffect(() => {
    const onPopState = () => {
      const route = readRouteFromLocation();
      dispatch({ type: "set-route-pane", pane: route.pane });
      dispatch({ type: "select-job", jobId: route.jobId });
      dispatch({ type: "set-selected-inspector-tab", tab: route.inspector });
    };

    window.addEventListener("popstate", onPopState);
    return () => window.removeEventListener("popstate", onPopState);
  }, [dispatch]);
}
