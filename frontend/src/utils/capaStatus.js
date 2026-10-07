// Mirrors CorrectiveAction's status sets in
// backend/apps/corrective_actions/models.py. The server is what enforces them —
// an owner posting anything outside its list gets a 403, with the message naming
// the status — so this exists only to stop the forms offering a value that will
// be refused. Keep the two in step when either changes.

// The owner reports how the work is going and files the evidence; what it
// amounts to is the auditor's to record. `evidence_submitted` is the handoff —
// "the work is done, here is the proof" — which is the owner's claim to make.
export const OWNER_REPORTABLE_STATUSES = [
    'in_progress', 'partially_resolved', 'evidence_submitted',
];

// The audit side records outcomes as well as progress, so its list adds the
// states that settle the action and the ones that assess it.
export const AUDIT_STATUSES = [
    'open', 'in_progress', 'partially_resolved', 'evidence_submitted',
    'resolved', 'not_implemented', 'closed',
];

// What verify-and-close may act on: everything except `closed` itself (nothing
// left to do) and `pending_approval` (the plan was never agreed, so there is no
// implementation to verify).
export const CLOSEABLE_FROM = [
    'open', 'in_progress', 'partially_resolved', 'evidence_submitted',
    'overdue', 'not_implemented', 'resolved',
];

/** The statuses a progress response may carry, for whoever is filling it in. */
export const responseStatusOptions = (canWriteAudit) => (
    canWriteAudit ? AUDIT_STATUSES : OWNER_REPORTABLE_STATUSES
);

export const canVerifyAndClose = (status) => CLOSEABLE_FROM.includes(status);
