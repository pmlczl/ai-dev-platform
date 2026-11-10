import { fetchWorkflow, resumeWorkflow } from './workflows'

import type { WorkflowApprovalRead, WorkflowRead } from '@/types'

/**
 * The approval actions of the platform.
 *
 * The platform has no dedicated approval endpoint: the decision of a human
 * is submitted through the resume endpoint of the workflow, because that is
 * the call that advances the run. This module only gives that flow a name,
 * so a page does not have to know how an approval is transported.
 */

/** The payload of an approval decision. */
export interface ApprovalPayload {
  /** The thread of the run - it comes from the backend, never from the browser. */
  thread_id: string
  decision: 'approved' | 'rejected'
  approver: string
  comment?: string | null
  /**
   * A client key that makes a repeated submission a no-op.
   *
   * The key belongs to one approval request: it is created once and reused
   * for every retry of that request.
   */
  idempotency_key?: string
}

/**
 * Submit the decision of a human approval.
 *
 * The backend validates the state of the run and the thread, stores the
 * decision and only then drives the graph.
 */
export async function submitWorkflowApproval(
  workflowId: string,
  payload: ApprovalPayload,
): Promise<WorkflowRead> {
  return resumeWorkflow(workflowId, payload)
}

/** Fetch the approval trail of one workflow run. */
export async function fetchWorkflowApprovals(
  workflowId: string,
): Promise<WorkflowApprovalRead[]> {
  const workflow = await fetchWorkflow(workflowId)
  return workflow.approvals
}
