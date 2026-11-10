import { http } from './client'

import type {
  Page,
  WorkflowEventRead,
  WorkflowRead,
  WorkflowResumeRequest,
  WorkflowStartRequest,
  WorkflowStatus,
} from '@/types'

/** Filters of the workflow list. */
export interface WorkflowListParams {
  page?: number
  page_size?: number
  status?: WorkflowStatus
  project_id?: string
  task_id?: string
}

/** Fetch one page of the workflow runs, newest first. */
export async function fetchWorkflows(
  params: WorkflowListParams = {},
): Promise<Page<WorkflowRead>> {
  const { data } = await http.get<Page<WorkflowRead>>('/workflows', { params })
  return data
}

/** Fetch the details of one workflow run. */
export async function fetchWorkflow(workflowId: string): Promise<WorkflowRead> {
  const { data } = await http.get<WorkflowRead>(`/workflows/${workflowId}`)
  return data
}

/**
 * Start a workflow for a task.
 *
 * The run is executed synchronously: the answer already carries the first
 * approval point. A task that runs a workflow already is answered with a
 * conflict that names the existing run.
 */
export async function startWorkflow(
  taskId: string,
  payload: WorkflowStartRequest = {},
): Promise<WorkflowRead> {
  const { data } = await http.post<WorkflowRead>(
    `/tasks/${taskId}/workflow/start`,
    payload,
  )
  return data
}

/**
 * Advance a workflow.
 *
 * `thread_id` is an assertion: it must be the thread the backend derived for
 * the run. It is never assembled by the browser.
 */
export async function resumeWorkflow(
  workflowId: string,
  payload: WorkflowResumeRequest,
): Promise<WorkflowRead> {
  const { data } = await http.post<WorkflowRead>(
    `/workflows/${workflowId}/resume`,
    payload,
  )
  return data
}

/** Fetch one page of the event log of a workflow run. */
export async function fetchWorkflowLogs(
  workflowId: string,
  params: { page?: number; page_size?: number } = {},
): Promise<Page<WorkflowEventRead>> {
  const { data } = await http.get<Page<WorkflowEventRead>>(
    `/workflows/${workflowId}/logs`,
    { params },
  )
  return data
}
