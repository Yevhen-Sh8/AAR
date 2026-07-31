"""Single place where anonymity policy is enforced (Wave 11, BUG-1/BUG-2).

Everything that could de-anonymise an `IndividualReport` is decided here and
nowhere else, so a reviewer has exactly one file to check.

Two layers, both purely at the *serialization* boundary:

  * `report_out`   — what a viewer sees on `GET/POST /aar/cases/{id}/reports`
  * `audit_payload` — what a viewer sees on `GET /audit/log`

Neither touches the database. `individual_reports.requested_for_user_id`
stays populated (the request-idempotency skip-set keys on it, and it is the
admin's only identity handle for an anonymous stub submission), and the
stored audit payload keeps the true originator so `entry_hash` still covers
it and `verify_chain()` — which reads rows directly — is unaffected.

The `reveal` flag is always computed from `core.rbac.optional_claims` +
`has_role(..., Role.ADMIN)`, which deliberately has NO dev bypass. Fail
closed: no token or a non-admin token ⇒ redacted.

KNOWN STRUCTURAL LIMIT (documented, not an oversight): a case with three
participants and one anonymous report narrows the author to three people no
matter what fields are hidden. That is why coverage reports
`anonymity_floor` instead of pretending the problem away.
"""
from __future__ import annotations

from typing import Any

from aar_api.models.aar import IndividualReport
from aar_api.models.audit import AuditAction
from aar_api.schemas.aar import IndividualReportOut


def report_out(
    row: IndividualReport,
    *,
    reveal: bool,
    case_function_counts: dict[str | None, int] | None = None,
) -> IndividualReportOut:
    """Serialise one report, redacting identity when it is anonymous.

    On an anonymous row seen by a non-admin:
      * `user_id` — already null on the row, kept null;
      * `requested_for_user_id` — hidden. THIS IS THE BUG-1 FIX: in the stub
        flow that column *is* the submitter's identity, and it used to be
        returned verbatim to every viewer;
      * `operator_id` — hidden (operator + function together are highly
        identifying — there is typically one manufacturer rep per operator);
      * `function` — hidden ONLY when this case holds exactly one report with
        that function (k>=2 within-case suppression: with a single commander
        in the case, the function alone names the person). Otherwise kept,
        because function coverage is the entire point of the feature.
      * `off_roster` — kept: it is a property of the *request*, not of the
        person.

    Server-side coverage aggregation reads the DB directly, so per-row
    suppression never distorts the metric.
    """
    out = IndividualReportOut.model_validate(row)
    if not row.anonymous or reveal:
        return out
    out.user_id = None
    out.requested_for_user_id = None
    out.operator_id = None
    if case_function_counts is not None and row.function is not None:
        key = row.function.value
        if case_function_counts.get(key, 0) <= 1:
            out.function = None
    return out


def function_counts(rows: list[IndividualReport]) -> dict[str | None, int]:
    """Within-case tally of report functions, for the k>=2 suppression rule.

    Computed from the already-fetched list — no extra query.
    """
    counts: dict[str | None, int] = {}
    for r in rows:
        key = r.function.value if r.function else None
        counts[key] = counts.get(key, 0) + 1
    return counts


def audit_payload(
    action: AuditAction, payload: dict[str, Any], *, reveal: bool
) -> dict[str, Any]:
    """Redact the originator of an anonymous report in the audit response.

    MANDATORY COMPANION to the BUG-2 fix: `GET /audit/log` is readable by
    ANALYSTS — the very people who read the testimony — and `AuditEntryOut`
    exposes `payload` verbatim. Writing the originator into the chain without
    this would simply move the leak.

    The stored row is never modified, so the hash chain still commits to the
    true originator and remains verifiable.
    """
    if action is not AuditAction.INDIVIDUAL_REPORT_SUBMITTED or reveal:
        return payload
    if not payload.get("anonymous"):
        return payload
    redacted = dict(payload)
    redacted["originator_user_id"] = None
    redacted["originator_redacted"] = True
    return redacted
