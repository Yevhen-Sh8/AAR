/** Shared shape of a listed usage event — the read model, with codes resolved. */
export interface UsageEventRow {
  id: number;
  client_event_id: string | null;
  event_date: string;
  outcome: "success" | "lost" | "repair";
  item_serial_no: string;
  item_type_code: string;
  operator_code: string;
  loss_reason_code: string | null;
  repair_reason_code: string | null;
  notes: string | null;
  aborted: boolean;
  abort_reason: string | null;
  recorded_at: string;
}

export const OUTCOME_UK: Record<UsageEventRow["outcome"], string> = {
  success: "успіх",
  lost: "втрата",
  repair: "ремонт",
};

export function outcomeBadge(o: UsageEventRow["outcome"]): string {
  return o === "success" ? "badge-green" : o === "lost" ? "badge-red" : "badge-gold";
}
