/**
 * Shared types + Ukrainian labels for the people directory (Wave 11).
 *
 * THE PROJECT AXIOM: `operator_id` is a person's DEFAULT affiliation. It may
 * order or highlight a list, it must NEVER be used to filter people out of a
 * participant pick unless the user explicitly asked for that filter.
 */

// Mirrors aar_api.models.user.ParticipantFunction
export type ParticipantFunction =
  | "crew"
  | "engineering"
  | "commander"
  | "ew_recon"
  | "manufacturer"
  | "other";

export const FUNCTION_LABELS: Record<ParticipantFunction, string> = {
  crew: "екіпаж",
  engineering: "інженерна обслуга",
  commander: "командир",
  ew_recon: "РЕБ-розвідка",
  manufacturer: "представник виробника",
  other: "інше",
};

export const FUNCTION_ORDER: ParticipantFunction[] = [
  "crew",
  "engineering",
  "commander",
  "ew_recon",
  "manufacturer",
  "other",
];

/** A missing function renders as «не вказано», never as a blank cell. */
export function functionLabel(f: string | null | undefined): string {
  if (!f) return "не вказано";
  return FUNCTION_LABELS[f as ParticipantFunction] ?? f;
}

// Mirrors aar_api.models.user.Role
export type Role = "participant" | "analyst" | "manager" | "admin" | "integrator";

export const ROLE_LABELS: Record<Role, string> = {
  participant: "учасник",
  analyst: "аналітик",
  manager: "менеджер",
  admin: "адміністратор",
  integrator: "інтегратор",
};

export const ROLE_ORDER: Role[] = [
  "participant",
  "analyst",
  "manager",
  "admin",
  "integrator",
];

/** Mirrors aar_api.schemas.people.PersonOut exactly. */
export interface PersonOut {
  id: number;
  full_name: string;
  callsign: string | null;
  email: string | null;
  role: Role;
  operator_id: number | null;
  function: ParticipantFunction | null;
  is_active: boolean;
  can_login: boolean;
  created_at: string;
}

export interface OperatorRow {
  id: number;
  code: string;
  name_uk: string;
}

/** Returned by POST /aar/cases/{id}/request-reports. */
export interface ReportRequestSummary {
  requested_count: number;
  skipped_existing: number;
  pending_report_ids: number[];
  function_coverage: Record<string, number>;
  missing_functions: string[];
  off_roster_user_ids: number[];
  warnings: string[];
}

/** apiFetch throws Error("API 409: ...detail..."); pull a human message out. */
export function errMessage(e: unknown): string {
  const raw = e instanceof Error ? e.message : String(e);
  const m = raw.match(/"detail":"([^"]+)"/);
  if (m) return m[1];
  if (raw.includes("409")) return "Конфлікт: запис уже існує або використовується.";
  if (raw.includes("403")) return "Недостатньо прав для цієї дії.";
  return "Помилка. Спробуйте ще раз.";
}

export function operatorLabel(
  operatorId: number | null | undefined,
  operators: OperatorRow[] | undefined,
): string {
  if (operatorId == null) return "—";
  const op = operators?.find((o) => o.id === operatorId);
  return op ? op.code : `#${operatorId}`;
}
