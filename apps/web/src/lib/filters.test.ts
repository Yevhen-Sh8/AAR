/**
 * Guards the class of bug where a filter <select> offers values that do not
 * exist in the backend StrEnum. The routers type those query params as the
 * enum, so a mismatch is not cosmetic: every selection returns 422, and in
 * ContextPage that failure used to render as "нічого не знайдено" — a broken
 * query and an empty result looked identical, which is how it went unnoticed.
 *
 * The expected sets are transcribed from:
 *   apps/api/aar_api/models/context.py  (ContextAssetType)
 *   apps/api/aar_api/models/audit.py    (AuditAction)
 * A new backend member does not fail this test; it only proves the frontend
 * never offers a value the backend would reject.
 */
import { describe, expect, it } from "vitest";

import { ACTION_GROUPS } from "../pages/AuditPage";
import { TYPE_FILTERS } from "../pages/ContextPage";

const CONTEXT_ASSET_TYPES = new Set([
  "business_rule",
  "failure_pattern",
  "edge_case",
  "acceptance_criterion",
  "architectural_decision",
  "deployment_lesson",
  "operator_practice",
  "training_gap",
]);

const AUDIT_ACTIONS = new Set([
  "event.created",
  "event.inbound",
  "case.created",
  "case.transitioned",
  "case.analysis_drafted",
  "case.closed",
  "recommendation.updated",
  "recommendation.auto_validated",
  "recommendation.regressed",
  "subscription.created",
  "subscription.deleted",
  "triggers.run",
  "context_asset.created",
  "context_asset.validated",
  "context_asset.rejected",
  "context_asset.deprecated",
  "signal.created",
  "signal.reviewed",
  "signal.converted",
  "dictionary.created",
  "dictionary.updated",
  "dictionary.deleted",
  "individual_report.requested",
  "individual_report.submitted",
  "person.created",
  "person.updated",
  "person.deleted",
  "person.password_set",
]);

describe("filter values match backend enums", () => {
  it("ContextPage type filters are real ContextAssetType members", () => {
    // "" is the deliberate "no filter" option — the router skips the param.
    const values = TYPE_FILTERS.map((f) => f.value).filter(Boolean);
    expect(values.length).toBeGreaterThan(0);
    for (const v of values) {
      expect(CONTEXT_ASSET_TYPES.has(v), `unknown ContextAssetType: ${v}`).toBe(true);
    }
  });

  it("AuditPage action filters are real AuditAction members", () => {
    const values = ACTION_GROUPS.flatMap((g) => g.items.map((i) => i.value));
    expect(values.length).toBeGreaterThan(0);
    for (const v of values) {
      expect(AUDIT_ACTIONS.has(v), `unknown AuditAction: ${v}`).toBe(true);
    }
  });

  it("audit actions are dotted, never underscored (the original bug)", () => {
    for (const g of ACTION_GROUPS) {
      for (const i of g.items) {
        expect(i.value, `${i.value} must be a dotted enum value`).toContain(".");
      }
    }
  });
});
