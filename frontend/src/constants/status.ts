/**
 * The presentation of the enums of the backend.
 *
 * The backend sends the raw values of its enumerations; the label and the
 * colour of every value are decided here - once. A tag and a select field
 * therefore always offer the same wording, and a page never writes the
 * mapping a second time.
 */
import type {
  ApprovalDecision,
  ArtifactReviewStatus,
  ProjectStatus,
  TaskPriority,
  TaskStatus,
  WorkflowStatus,
} from '@/types'

/** The colours a tag of Element Plus knows. */
export type TagType = 'primary' | 'success' | 'info' | 'warning' | 'danger'

/** How one value of an enumeration is presented. */
export interface StatusEntry {
  label: string
  type: TagType
}

/** The groups of statuses the platform knows. */
export type StatusKind = 'project' | 'task' | 'workflow' | 'artifact'

/** One option of a select field that filters by a status. */
export interface StatusOption {
  value: string
  label: string
}

/** The status of every group. */
export const STATUS_MAPS: Record<StatusKind, Record<string, StatusEntry>> = {
  project: {
    planning: { label: '规划中', type: 'info' },
    active: { label: '进行中', type: 'primary' },
    paused: { label: '已暂停', type: 'warning' },
    completed: { label: '已完成', type: 'success' },
    archived: { label: '已归档', type: 'info' },
    cancelled: { label: '已取消', type: 'danger' },
  },
  task: {
    pending: { label: '待处理', type: 'info' },
    in_progress: { label: '开发中', type: 'primary' },
    blocked: { label: '已阻塞', type: 'danger' },
    in_review: { label: '待审核', type: 'warning' },
    completed: { label: '已完成', type: 'success' },
    cancelled: { label: '已取消', type: 'info' },
  },
  workflow: {
    pending: { label: '待启动', type: 'info' },
    running: { label: '执行中', type: 'primary' },
    paused: { label: '已暂停', type: 'warning' },
    waiting_approval: { label: '待审批', type: 'warning' },
    completed: { label: '已完成', type: 'success' },
    failed: { label: '已失败', type: 'danger' },
    cancelled: { label: '已取消', type: 'info' },
  },
  artifact: {
    pending: { label: '待审核', type: 'info' },
    approved: { label: '已通过', type: 'success' },
    rejected: { label: '已驳回', type: 'danger' },
    superseded: { label: '已被替换', type: 'info' },
  },
}

/** The approval decisions - they are shown next to the artifact states. */
export const DECISION_MAP: Record<string, StatusEntry> = {
  approved: { label: '已通过', type: 'success' },
  rejected: { label: '已驳回', type: 'danger' },
  changes_requested: { label: '要求修改', type: 'warning' },
}

/** The priorities of a task. */
export const PRIORITY_MAP: Record<string, StatusEntry> = {
  low: { label: '低', type: 'info' },
  medium: { label: '中', type: 'info' },
  high: { label: '高', type: 'warning' },
  urgent: { label: '紧急', type: 'danger' },
}

/**
 * The options of a select field that filters by a status.
 *
 * The order follows the enumeration of the backend, so the filter offers the
 * statuses in the order of the life cycle.
 */
export function statusOptions(kind: StatusKind): StatusOption[] {
  return Object.entries(STATUS_MAPS[kind]).map(([value, entry]) => ({
    value,
    label: entry.label,
  }))
}

/** The label of a status - the raw value is returned when it is unknown. */
export function statusLabel(kind: StatusKind, value: string): string {
  return STATUS_MAPS[kind][value]?.label ?? value
}

/** The projects that the platform knows - used by the filter of the list. */
export const PROJECT_STATUS_OPTIONS: StatusOption[] = statusOptions('project')

/** The types of the project status - the filter needs them for its value. */
export const PROJECT_STATUS_VALUES: ProjectStatus[] = PROJECT_STATUS_OPTIONS.map(
  (option) => option.value as ProjectStatus,
)

/** The task status values - kept next to the project ones for symmetry. */
export const TASK_STATUS_VALUES: TaskStatus[] = Object.keys(
  STATUS_MAPS.task,
) as TaskStatus[]

/** The workflow status values. */
export const WORKFLOW_STATUS_VALUES: WorkflowStatus[] = Object.keys(
  STATUS_MAPS.workflow,
) as WorkflowStatus[]

/** The review states of an artifact. */
export const ARTIFACT_REVIEW_STATUS_VALUES: ArtifactReviewStatus[] = Object.keys(
  STATUS_MAPS.artifact,
) as ArtifactReviewStatus[]

/** The outcomes of an approval. */
export const APPROVAL_DECISION_VALUES: ApprovalDecision[] = Object.keys(
  DECISION_MAP,
) as ApprovalDecision[]

/** The priorities of a task. */
export const TASK_PRIORITY_VALUES: TaskPriority[] = Object.keys(
  PRIORITY_MAP,
) as TaskPriority[]
