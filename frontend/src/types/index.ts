/**
 * Shared DTOs of the backend API.
 *
 * The fields mirror the Pydantic schemas of the backend one to one. The
 * backend is the only source of truth for a field: nothing is invented here,
 * and a value that the backend does not send is typed as `null` instead of
 * being defaulted.
 */

/** Envelope of every paginated list endpoint. */
export interface Page<T> {
  items: T[]
  total: number
  page: number
  page_size: number
  pages: number
}

/** Lifecycle of a project. */
export type ProjectStatus =
  | 'planning'
  | 'active'
  | 'paused'
  | 'completed'
  | 'archived'
  | 'cancelled'

/** Lifecycle of a development task. */
export type TaskStatus =
  | 'pending'
  | 'in_progress'
  | 'blocked'
  | 'in_review'
  | 'completed'
  | 'cancelled'

/** Relative priority of a development task. */
export type TaskPriority = 'low' | 'medium' | 'high' | 'urgent'

/** Lifecycle of a workflow instance. */
export type WorkflowStatus =
  | 'pending'
  | 'running'
  | 'paused'
  | 'waiting_approval'
  | 'completed'
  | 'failed'
  | 'cancelled'

/** Review state of an artifact. */
export type ArtifactReviewStatus = 'pending' | 'approved' | 'rejected' | 'superseded'

/** Development stage an artifact belongs to. */
export type ArtifactStage = 'design' | 'development' | 'testing' | 'delivery' | 'other'

/** Outcome of a single approval record. */
export type ApprovalDecision = 'approved' | 'rejected' | 'changes_requested'

/** Kind of object an approval record refers to. */
export type ApprovalTargetType = 'task' | 'artifact' | 'workflow_instance'

/** A project as returned by the API. */
export interface ProjectRead {
  id: string
  code: string
  name: string
  description: string | null
  status: ProjectStatus
  owner: string | null
  created_at: string
  updated_at: string
}

/** A project in a list, enriched with the number of its tasks. */
export interface ProjectListItem extends ProjectRead {
  task_count: number
}

/** Payload for creating a project. */
export interface ProjectCreate {
  code: string
  name: string
  description?: string | null
  status?: ProjectStatus
  owner?: string | null
}

/** Payload for updating a project - only the fields that are present are written. */
export interface ProjectUpdate {
  code?: string
  name?: string
  description?: string | null
  status?: ProjectStatus
  owner?: string | null
}

/** A development task as returned by the API. */
export interface TaskRead {
  id: string
  project_id: string
  seq: number
  title: string
  description: string | null
  status: TaskStatus
  priority: TaskPriority
  assignee: string | null
  project_code: string | null
  project_name: string | null
  created_at: string
  updated_at: string
}

/** Payload for creating a development task. */
export interface TaskCreate {
  project_id: string
  title: string
  description?: string | null
  status?: TaskStatus
  priority?: TaskPriority
  assignee?: string | null
}

/** Payload for updating a development task. */
export interface TaskUpdate {
  title?: string
  description?: string | null
  status?: TaskStatus
  priority?: TaskPriority
  assignee?: string | null
}

/** An artifact as returned by the API. */
export interface ArtifactRead {
  id: string
  project_id: string
  task_id: string | null
  workflow_instance_id: string | null
  relative_path: string
  version: number
  sha256: string
  file_type: string
  size_bytes: number | null
  review_status: ArtifactReviewStatus
  reviewed_by: string | null
  reviewed_at: string | null
  created_by: string | null
  stage: ArtifactStage
  original_filename: string | null
  storage_path: string | null
  created_at: string
  updated_at: string
}

/** Payload for the review of an artifact. */
export interface ArtifactReviewRequest {
  decision: 'approved' | 'rejected'
  reviewed_by: string
  comment?: string | null
}

/** The artifact of the current round of a workflow. */
export interface WorkflowArtifactRead {
  id: string
  relative_path: string
  version: number
  sha256: string
  size_bytes: number | null
  review_status: ArtifactReviewStatus
}

/** Summary of the approval a workflow is waiting for. */
export interface PendingApproval {
  request_id: string
  iteration: number
  artifact_id: string | null
  artifact_version: number | null
  preview: string
  revision_comments: string[]
  requested_at: string | null
}

/** One decision of the approval trail of a workflow. */
export interface WorkflowApprovalRead {
  id: string
  decision: ApprovalDecision
  approver: string
  comment: string | null
  sequence: number
  created_at: string
}

/** The view of a workflow instance - never the state of the graph. */
export interface WorkflowRead {
  id: string
  project_id: string
  task_id: string | null
  workflow_key: string
  thread_id: string
  status: WorkflowStatus
  current_step: string | null
  iteration: number
  current_artifact: WorkflowArtifactRead | null
  pending_approval: PendingApproval | null
  approvals: WorkflowApprovalRead[]
  started_at: string | null
  finished_at: string | null
  error_message: string | null
  created_at: string
  updated_at: string
}

/** One entry of the event log of a workflow. */
export interface WorkflowEventRead {
  sequence: number
  step: string
  event: string
  message: string | null
  payload: Record<string, unknown> | null
  created_at: string
}

/** Payload for starting a workflow. */
export interface WorkflowStartRequest {
  workflow_key?: string
  started_by?: string
}

/** Payload for advancing a workflow - `thread_id` is an assertion. */
export interface WorkflowResumeRequest {
  thread_id: string
  decision?: 'approved' | 'rejected'
  approver?: string
  comment?: string | null
  idempotency_key?: string
}

/** An approval record as returned by the API. */
export interface ApprovalRecordRead {
  id: string
  project_id: string
  target_type: ApprovalTargetType
  target_id: string
  decision: ApprovalDecision
  comment: string | null
  approver: string
  sequence: number
  created_at: string
}

/** The unified error envelope returned by the backend. */
export interface ApiErrorPayload {
  code: string
  message: string
  detail?: unknown
  request_id?: string
  timestamp?: string
}
