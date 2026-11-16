/**
 * The presentation of the workflow graph of the backend.
 *
 * The node names are the ones of `backend/app/workflows/dev_workflow.py`.
 * The frontend only labels them - which node a run is in, and which nodes
 * were passed, is always read from the backend (the instance and its event
 * log), never computed here.
 */
import type { WorkflowStatus } from '@/types'

/** One node of the graph. */
export interface WorkflowNodeInfo {
  key: string
  label: string
  description: string
}

/**
 * The main path of the graph, in the order a run passes it.
 *
 * `handle_revision_comments` and `fail_workflow` are branches: they are shown
 * only when the event log says the run went through them.
 */
export const WORKFLOW_MAIN_PATH: WorkflowNodeInfo[] = [
  { key: 'load_task', label: '加载任务', description: '读取任务与项目信息' },
  {
    key: 'generate_demo_artifact',
    label: '生成模拟产物',
    description: '按固定模板生成演示文档（本地模拟，不调用模型）',
  },
  { key: 'validate_artifact', label: '校验产物', description: '校验文件、摘要与必需章节' },
  { key: 'human_approval', label: '人工审批', description: '等待审批人通过或驳回' },
  { key: 'complete_workflow', label: '完成', description: '工作流结束' },
]

/** The branch nodes of the graph. */
export const WORKFLOW_BRANCH_NODES: Record<string, WorkflowNodeInfo> = {
  handle_revision_comments: {
    key: 'handle_revision_comments',
    label: '处理修改意见',
    description: '驳回后记录意见并进入下一轮',
  },
  fail_workflow: {
    key: 'fail_workflow',
    label: '失败',
    description: '任务无效或校验多次不通过',
  },
  recover: {
    key: 'recover',
    label: '重启恢复',
    description: '服务重启后恢复实例状态',
  },
}

/** The label of a node - the raw name is returned when it is unknown. */
export function workflowNodeLabel(step?: string | null): string {
  if (!step) {
    return '—'
  }
  const main = WORKFLOW_MAIN_PATH.find((node) => node.key === step)
  if (main) {
    return main.label
  }
  return WORKFLOW_BRANCH_NODES[step]?.label ?? step
}

/** The labels of the events of the log. */
export const WORKFLOW_EVENT_LABELS: Record<string, string> = {
  node_started: '节点开始',
  artifact_generated: '产物已生成',
  validation_passed: '校验通过',
  validation_failed: '校验失败',
  approval_requested: '发起审批',
  approval_received: '收到审批结果',
  revision_handled: '已处理修改意见',
  workflow_completed: '工作流完成',
  workflow_failed: '工作流失败',
  workflow_recovered: '重启后恢复',
}

/** The label of an event - the raw name is returned when it is unknown. */
export function workflowEventLabel(event: string): string {
  return WORKFLOW_EVENT_LABELS[event] ?? event
}

/** Events that mark a problem. */
export const WORKFLOW_ERROR_EVENTS = new Set(['validation_failed', 'workflow_failed'])

/** The labels of the workflow types the backend registers. */
export const WORKFLOW_KEY_LABELS: Record<string, string> = {
  dev_workflow: '研发工作流（模拟）',
}

/** The label of a workflow type. */
export function workflowKeyLabel(key: string): string {
  return WORKFLOW_KEY_LABELS[key] ?? key
}

/** Statuses in which a run can still change - a page polls them. */
export const WORKFLOW_LIVE_STATUSES: WorkflowStatus[] = [
  'pending',
  'running',
  'waiting_approval',
  'paused',
]

/** Statuses in which a run is finished. */
export const WORKFLOW_TERMINAL_STATUSES: WorkflowStatus[] = [
  'completed',
  'failed',
  'cancelled',
]

/** True when the run can still change. */
export function isWorkflowLive(status: WorkflowStatus): boolean {
  return WORKFLOW_LIVE_STATUSES.includes(status)
}

/** True when the run is finished. */
export function isWorkflowTerminal(status: WorkflowStatus): boolean {
  return WORKFLOW_TERMINAL_STATUSES.includes(status)
}

/** The interval of the polling of a live run, in milliseconds. */
export const WORKFLOW_POLL_INTERVAL_MS = 4000
