/**
 * The rules of a human approval decision.
 *
 * The limits are the ones of `WorkflowResumeRequest` in
 * `backend/app/schemas/workflow.py`: the page refuses a value the backend
 * would refuse, and the backend stays the authority. The platform has no
 * authentication, so the approver is a self-reported name that is recorded
 * as it is typed - it is never presented as a verified identity.
 */

/** `approver` of `WorkflowResumeRequest` - `max_length=120`. */
export const APPROVER_MAX_LENGTH = 120

/** `comment` of `WorkflowResumeRequest` - `max_length=5000`. */
export const DECISION_COMMENT_MAX_LENGTH = 5000

/** `idempotency_key` of `WorkflowResumeRequest` - `max_length=100`. */
export const IDEMPOTENCY_KEY_MAX_LENGTH = 100

/**
 * The interval at which the queue of waiting runs is loaded again, in
 * milliseconds.
 *
 * A run leaves the queue as soon as anybody decides it, and the platform has
 * no push channel, so the list asks the backend on a timer. Five seconds is
 * the interval the implementation plan names for the todo list; it is longer
 * than the polling of a single running workflow because the queue only shows
 * runs that wait for a human and nothing changes on its own.
 */
export const APPROVAL_QUEUE_POLL_INTERVAL_MS = 5000

/**
 * The client key of one approval request.
 *
 * The backend accepts `^[A-Za-z0-9._:-]+$` and treats a repeated key as a
 * replay, so a page that retries a lost request cannot store the same
 * decision twice. The key is derived from the approval request the backend
 * announced (`pending_approval.request_id`, itself `workflow:iteration`) and
 * from the decision the user picked, so that approving and then rejecting
 * the same round are two different requests.
 */
export function approvalIdempotencyKey(
  requestId: string,
  decision: 'approved' | 'rejected',
): string {
  const cleaned = `${requestId}:${decision}`.replace(/[^A-Za-z0-9._:-]/g, '-')
  return `web-${cleaned}`.slice(0, IDEMPOTENCY_KEY_MAX_LENGTH)
}
