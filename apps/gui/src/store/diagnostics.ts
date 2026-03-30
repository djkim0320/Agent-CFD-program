import type { DiagnosticIssue, DiagnosticScope, DiagnosticSeverity, StreamHealth, StreamHealthState } from "../lib/types";

export interface DiagnosticIssueInput {
  scope: DiagnosticScope;
  code: string;
  title: string;
  detail: string;
  severity: DiagnosticSeverity;
  subjectId?: string | null;
  impact?: string | null;
  nextAction?: string | null;
  raw?: unknown;
}

export function createDiagnosticIssue(input: DiagnosticIssueInput): DiagnosticIssue {
  const createdAt = new Date().toISOString();
  const randomId =
    typeof globalThis.crypto?.randomUUID === "function"
      ? globalThis.crypto.randomUUID()
      : `${Date.now()}-${Math.random().toString(16).slice(2)}`;
  return {
    id: `diagnostic-${randomId}`,
    scope: input.scope,
    subjectId: input.subjectId ?? null,
    code: input.code,
    title: input.title,
    detail: input.detail,
    severity: input.severity,
    impact: input.impact ?? null,
    nextAction: input.nextAction ?? null,
    raw: input.raw ?? null,
    createdAt,
  };
}

export function formatIssueNotice(issue: DiagnosticIssue): string {
  return `${issue.title}: ${issue.detail}`;
}

export function createIdleStreamHealth(): StreamHealth {
  return {
    state: "idle",
    lastEventAt: null,
    lastError: null,
    eventCount: 0,
  };
}

export function updateStreamHealth(
  current: StreamHealth | undefined,
  nextState: StreamHealthState,
  patch?: Partial<StreamHealth>,
): StreamHealth {
  return {
    state: nextState,
    lastEventAt: patch?.lastEventAt ?? current?.lastEventAt ?? null,
    lastError: patch?.lastError ?? current?.lastError ?? null,
    eventCount: patch?.eventCount ?? current?.eventCount ?? 0,
  };
}
