<script setup lang="ts">
/**
 * The detail of one workflow run.
 *
 * The page shows the state of the run as the backend reports it, the path it
 * took through the graph and its event log. While the run is still going the
 * page polls the backend - one request at a time, never after the page was
 * left - and it stops as soon as the run reached a final state.
 *
 * A run that waits for an approval is handed to the approval page; a run the
 * backend paused after a restart is continued from here. There is no way to
 * pause a run: the backend has no such operation.
 */
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'

import PageHeader from '@/components/common/PageHeader.vue'
import PageState from '@/components/common/PageState.vue'
import StatusTag from '@/components/common/StatusTag.vue'
import WorkflowEventTable from '@/components/workflow/WorkflowEventTable.vue'
import WorkflowNodePath from '@/components/workflow/WorkflowNodePath.vue'
import { downloadArtifact } from '@/api/artifacts'
import { describeApiError, isNotFoundError } from '@/api/client'
import { fetchWorkflow, fetchWorkflowLogs, resumeWorkflow } from '@/api/workflows'
import {
  WORKFLOW_POLL_INTERVAL_MS,
  isWorkflowLive,
  isWorkflowTerminal,
  workflowKeyLabel,
  workflowNodeLabel,
} from '@/constants/workflow'
import { useReferenceStore, useWorkspaceStore } from '@/stores'
import { saveBlob } from '@/utils/download'
import { formatDateTime, formatFileName, formatFileSize } from '@/utils/format'

import type { WorkflowEventRead, WorkflowRead } from '@/types'

/** The log is read in pages of this size - the whole log is needed for the path. */
const LOG_FETCH_SIZE = 100
/** The rows of the event table per page. */
const EVENT_PAGE_SIZE = 20

const route = useRoute()
const router = useRouter()
const workspace = useWorkspaceStore()
const reference = useReferenceStore()

const workflowId = computed(() => String(route.params.workflow_id ?? ''))

// --- the run --------------------------------------------------------------------

const workflow = ref<WorkflowRead | null>(null)
const events = ref<WorkflowEventRead[]>([])
const loading = ref(false)
const error = ref<string | null>(null)
/** The backend answered 404: the run does not exist. */
const missing = ref(false)
/** The error of a poll - the page keeps what it has and says so. */
const pollError = ref<string | null>(null)
const refreshedAt = ref<string | null>(null)

let inflight: Promise<void> | null = null

/** Read the whole log of the run, oldest first. */
async function loadAllEvents(): Promise<WorkflowEventRead[]> {
  const first = await fetchWorkflowLogs(
    workflowId.value,
    { page: 1, page_size: LOG_FETCH_SIZE },
    { silent: true },
  )
  if (first.pages <= 1) {
    return first.items
  }
  const rest = await Promise.all(
    Array.from({ length: first.pages - 1 }, (_, index) =>
      fetchWorkflowLogs(
        workflowId.value,
        { page: index + 2, page_size: LOG_FETCH_SIZE },
        { silent: true },
      ),
    ),
  )
  return [...first.items, ...rest.flatMap((page) => page.items)]
}

/**
 * Load the run and its log.
 *
 * `background` marks a poll: the page keeps what it shows while the request
 * runs, and a failure is shown next to it instead of replacing it.
 */
async function load(background = false): Promise<void> {
  if (inflight) {
    return inflight
  }
  if (!background) {
    loading.value = true
    error.value = null
    missing.value = false
  }
  inflight = (async () => {
    try {
      const [run, log] = await Promise.all([
        fetchWorkflow(workflowId.value, { silent: true }),
        loadAllEvents(),
      ])
      workflow.value = run
      events.value = log
      refreshedAt.value = new Date().toISOString()
      pollError.value = null
      error.value = null
      workspace.focusWorkflow(run.id)
      workspace.workflow = run
      await Promise.all([
        reference.resolveProjects([run.project_id]),
        reference.resolveTasks([run.task_id]),
      ])
    } catch (caught) {
      if (background) {
        pollError.value = describeApiError(caught)
      } else {
        workflow.value = null
        events.value = []
        if (isNotFoundError(caught)) {
          missing.value = true
        }
        error.value = describeApiError(caught)
      }
    } finally {
      loading.value = false
      inflight = null
    }
  })()
  return inflight
}

const project = computed(() =>
  workflow.value ? (reference.projects[workflow.value.project_id] ?? null) : null,
)
const task = computed(() =>
  workflow.value?.task_id ? (reference.tasks[workflow.value.task_id] ?? null) : null,
)

const isLive = computed(() => Boolean(workflow.value && isWorkflowLive(workflow.value.status)))
const isTerminal = computed(() =>
  Boolean(workflow.value && isWorkflowTerminal(workflow.value.status)),
)

// --- polling --------------------------------------------------------------------------

let pollTimer: number | null = null
let unmounted = false

function stopPolling(): void {
  if (pollTimer !== null) {
    window.clearTimeout(pollTimer)
    pollTimer = null
  }
}

function schedulePoll(): void {
  stopPolling()
  if (unmounted || !isLive.value) {
    return
  }
  pollTimer = window.setTimeout(async () => {
    pollTimer = null
    if (unmounted || route.name !== 'workflow-detail') {
      return
    }
    await load(true)
    schedulePoll()
  }, WORKFLOW_POLL_INTERVAL_MS)
}

watch(isLive, () => schedulePoll())

onBeforeUnmount(() => {
  unmounted = true
  stopPolling()
})

// --- the actions ----------------------------------------------------------------------

const resuming = ref(false)

/** Continue a run the backend paused when it was restarted. */
async function handleResume(): Promise<void> {
  const run = workflow.value
  if (!run || resuming.value || run.status !== 'paused') {
    return
  }
  try {
    await ElMessageBox.confirm(
      '该运行在服务重启后处于暂停状态。继续执行会从检查点恢复，确定继续？',
      '继续执行',
      { confirmButtonText: '继续执行', cancelButtonText: '取消', type: 'warning' },
    )
  } catch {
    return
  }
  resuming.value = true
  try {
    // The thread id is the one the backend reported for the run.
    await resumeWorkflow(run.id, { thread_id: run.thread_id })
    ElMessage.success('已继续执行')
  } catch {
    // The interceptor of the client already told the user what went wrong.
  } finally {
    resuming.value = false
    await load()
    schedulePoll()
  }
}

function goToApproval(): void {
  if (!workflow.value) {
    return
  }
  void router.push({ name: 'approval-detail', params: { workflow_id: workflow.value.id } })
}

function goToTask(): void {
  if (!workflow.value?.task_id) {
    return
  }
  workspace.focusTask(workflow.value.task_id)
  void router.push({ name: 'task-detail', params: { task_id: workflow.value.task_id } })
}

function goToProject(): void {
  if (!workflow.value) {
    return
  }
  workspace.focusProject(workflow.value.project_id)
  void router.push({ name: 'project-detail', params: { project_id: workflow.value.project_id } })
}

const downloadingArtifact = ref(false)

/** Download the file of the current round through the backend. */
async function handleDownloadArtifact(): Promise<void> {
  const artifact = workflow.value?.current_artifact
  if (!artifact || downloadingArtifact.value) {
    return
  }
  downloadingArtifact.value = true
  try {
    const result = await downloadArtifact(artifact.id)
    saveBlob(result.blob, result.filename ?? formatFileName(artifact.relative_path, artifact.id))
  } catch {
    // The interceptor of the client already told the user what went wrong.
  } finally {
    downloadingArtifact.value = false
  }
}

// --- the event table ---------------------------------------------------------------------

const eventPage = ref(1)

const pagedEvents = computed(() => {
  const start = (eventPage.value - 1) * EVENT_PAGE_SIZE
  return events.value.slice(start, start + EVENT_PAGE_SIZE)
})

watch(
  () => events.value.length,
  (length) => {
    const pages = Math.max(1, Math.ceil(length / EVENT_PAGE_SIZE))
    if (eventPage.value > pages) {
      eventPage.value = pages
    }
  },
)

// --- loading ----------------------------------------------------------------------------------

function shortId(id: string): string {
  return id.split('-')[0]
}

watch(
  workflowId,
  async () => {
    if (route.name !== 'workflow-detail') {
      return
    }
    eventPage.value = 1
    await load()
    schedulePoll()
  },
  { immediate: true },
)
</script>

<template>
  <div class="workflow-detail">
    <PageState
      v-if="(loading && !workflow) || error"
      :loading="loading && !workflow"
      :error="error"
      loading-text="正在加载工作流…"
      min-height="320px"
    >
      <template #error>
        <p v-if="missing" class="workflow-detail__hint">该工作流运行不存在。</p>
        <div class="workflow-detail__error-actions">
          <el-button @click="router.push({ name: 'workflows' })">返回工作流监控</el-button>
          <el-button v-if="!missing" type="primary" plain @click="load()">重试</el-button>
        </div>
      </template>
    </PageState>

    <template v-else-if="workflow">
      <PageHeader
        :title="`工作流 ${shortId(workflow.id)}`"
        :subtitle="workflowKeyLabel(workflow.workflow_key)"
        :back-to="{ name: 'workflows' }"
        back-text="工作流监控"
      >
        <template #tags>
          <StatusTag :status="workflow.status" kind="workflow" />
          <el-tag v-if="isLive" size="small" effect="plain" type="info" class="workflow-detail__poll-tag">
            每 {{ WORKFLOW_POLL_INTERVAL_MS / 1000 }} 秒自动刷新
          </el-tag>
        </template>
        <template #actions>
          <el-button :loading="loading" @click="load()">
            <el-icon><Refresh /></el-icon>
            <span>刷新</span>
          </el-button>
          <el-button v-if="workflow.task_id" @click="goToTask">查看任务</el-button>
          <el-button
            v-if="workflow.status === 'paused'"
            type="primary"
            :loading="resuming"
            :disabled="resuming"
            @click="handleResume"
          >
            <el-icon><VideoPlay /></el-icon>
            <span>继续执行</span>
          </el-button>
          <el-button v-if="workflow.status === 'waiting_approval'" type="primary" @click="goToApproval">
            <el-icon><Stamp /></el-icon>
            <span>前往审批</span>
          </el-button>
        </template>
      </PageHeader>

      <el-alert
        v-if="pollError"
        type="warning"
        :closable="false"
        show-icon
        class="workflow-detail__alert"
        :title="`自动刷新失败，页面可能不是最新：${pollError}`"
      />

      <el-alert
        v-if="workflow.status === 'waiting_approval'"
        type="warning"
        :closable="false"
        show-icon
        class="workflow-detail__alert"
        title="该运行正在等待人工审批，审批通过或驳回后才会继续。"
      />

      <el-alert
        v-if="workflow.error_message"
        type="error"
        :closable="false"
        show-icon
        class="workflow-detail__alert"
        title="后端报告的错误"
        :description="workflow.error_message"
      />

      <el-card shadow="never" class="workflow-detail__card">
        <template #header>
          <span class="workflow-detail__card-title">基本信息</span>
        </template>
        <el-descriptions :column="3" border size="default">
          <el-descriptions-item label="工作流 ID">
            <span class="workflow-detail__mono">{{ workflow.id }}</span>
          </el-descriptions-item>
          <el-descriptions-item label="所属项目">
            <el-link type="primary" underline="never" @click="goToProject">
              {{ project ? project.name : shortId(workflow.project_id) }}
            </el-link>
            <span v-if="project" class="workflow-detail__muted"> ({{ project.code }})</span>
          </el-descriptions-item>
          <el-descriptions-item label="所属任务">
            <template v-if="workflow.task_id">
              <el-link type="primary" underline="never" @click="goToTask">
                {{ task ? `#${task.seq} ${task.title}` : shortId(workflow.task_id) }}
              </el-link>
            </template>
            <span v-else>—</span>
          </el-descriptions-item>
          <el-descriptions-item label="类型">{{ workflowKeyLabel(workflow.workflow_key) }}</el-descriptions-item>
          <el-descriptions-item label="状态">
            <StatusTag :status="workflow.status" kind="workflow" />
          </el-descriptions-item>
          <el-descriptions-item label="当前节点">
            {{ workflowNodeLabel(workflow.current_step) }}
            <span v-if="workflow.current_step" class="workflow-detail__muted workflow-detail__mono">
              ({{ workflow.current_step }})
            </span>
          </el-descriptions-item>
          <el-descriptions-item label="轮次">第 {{ workflow.iteration }} 轮</el-descriptions-item>
          <el-descriptions-item label="线程 ID" :span="2">
            <span class="workflow-detail__mono">{{ workflow.thread_id }}</span>
          </el-descriptions-item>
          <el-descriptions-item label="开始时间">{{ formatDateTime(workflow.started_at) }}</el-descriptions-item>
          <el-descriptions-item label="最后更新">{{ formatDateTime(workflow.updated_at) }}</el-descriptions-item>
          <el-descriptions-item label="结束时间">
            {{ isTerminal ? formatDateTime(workflow.finished_at) : '—' }}
          </el-descriptions-item>
        </el-descriptions>
      </el-card>

      <el-card shadow="never" class="workflow-detail__card">
        <template #header>
          <div class="workflow-detail__card-header">
            <span class="workflow-detail__card-title">执行节点</span>
            <span class="workflow-detail__muted">
              节点状态来自后端的运行状态与事件日志
              <template v-if="refreshedAt"> · 更新于 {{ formatDateTime(refreshedAt) }}</template>
            </span>
          </div>
        </template>
        <WorkflowNodePath :workflow="workflow" :events="events" />
      </el-card>

      <el-card v-if="workflow.current_artifact || workflow.pending_approval" shadow="never" class="workflow-detail__card">
        <template #header>
          <span class="workflow-detail__card-title">本轮产物</span>
          <el-tag size="small" type="warning" effect="plain" class="workflow-detail__sim-tag">模拟成果</el-tag>
        </template>
        <el-descriptions :column="3" border size="default">
          <template v-if="workflow.current_artifact">
            <el-descriptions-item label="文件">
              <span class="workflow-detail__filename" :title="workflow.current_artifact.relative_path">
                {{ formatFileName(workflow.current_artifact.relative_path) }}
              </span>
            </el-descriptions-item>
            <el-descriptions-item label="版本">v{{ workflow.current_artifact.version }}</el-descriptions-item>
            <el-descriptions-item label="大小">
              {{ formatFileSize(workflow.current_artifact.size_bytes) }}
            </el-descriptions-item>
            <el-descriptions-item label="审核状态">
              <StatusTag :status="workflow.current_artifact.review_status" kind="artifact" />
            </el-descriptions-item>
            <el-descriptions-item label="SHA-256" :span="2">
              <span class="workflow-detail__mono workflow-detail__sha">{{ workflow.current_artifact.sha256 }}</span>
            </el-descriptions-item>
          </template>
          <template v-if="workflow.pending_approval">
            <el-descriptions-item label="审批请求">
              <span class="workflow-detail__mono">{{ workflow.pending_approval.request_id }}</span>
            </el-descriptions-item>
            <el-descriptions-item label="发起时间">
              {{ formatDateTime(workflow.pending_approval.requested_at) }}
            </el-descriptions-item>
            <el-descriptions-item label="历史修改意见">
              {{ workflow.pending_approval.revision_comments.length }} 条
            </el-descriptions-item>
          </template>
        </el-descriptions>
        <div class="workflow-detail__artifact-actions">
          <el-button
            v-if="workflow.current_artifact"
            :loading="downloadingArtifact"
            @click="handleDownloadArtifact"
          >
            <el-icon><Download /></el-icon>
            <span>下载产物</span>
          </el-button>
          <el-button v-if="workflow.status === 'waiting_approval'" type="primary" @click="goToApproval">
            前往审批
          </el-button>
        </div>
      </el-card>

      <el-card v-if="workflow.approvals.length > 0" shadow="never" class="workflow-detail__card">
        <template #header>
          <span class="workflow-detail__card-title">审批记录</span>
          <span class="workflow-detail__card-count">共 {{ workflow.approvals.length }} 条</span>
        </template>
        <el-table class="workflow-approvals" :data="workflow.approvals" row-key="id" stripe style="width: 100%">
          <el-table-column label="序号" prop="sequence" width="64" align="center" />
          <el-table-column label="结果" width="100" align="center">
            <template #default="{ row }">
              <StatusTag :status="row.decision" kind="decision" />
            </template>
          </el-table-column>
          <el-table-column label="审批人" prop="approver" width="140" show-overflow-tooltip />
          <el-table-column label="意见" min-width="240" show-overflow-tooltip>
            <template #default="{ row }">{{ row.comment || '—' }}</template>
          </el-table-column>
          <el-table-column label="时间" width="160">
            <template #default="{ row }">{{ formatDateTime(row.created_at) }}</template>
          </el-table-column>
        </el-table>
      </el-card>

      <el-card shadow="never" class="workflow-detail__card">
        <template #header>
          <div class="workflow-detail__card-header">
            <div>
              <span class="workflow-detail__card-title">事件日志</span>
              <span class="workflow-detail__card-count">共 {{ events.length }} 条 · 按时间先后排列</span>
            </div>
          </div>
        </template>
        <PageState :empty="events.length === 0" empty-text="还没有事件记录" min-height="120px">
          <WorkflowEventTable :events="pagedEvents" />
          <div v-if="events.length > EVENT_PAGE_SIZE" class="workflow-detail__pagination">
            <el-pagination
              v-model:current-page="eventPage"
              background
              layout="total, prev, pager, next"
              :total="events.length"
              :page-size="EVENT_PAGE_SIZE"
            />
          </div>
        </PageState>
      </el-card>
    </template>
  </div>
</template>

<style scoped>
.workflow-detail__card {
  margin-bottom: 16px;
}

.workflow-detail__card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  flex-wrap: wrap;
}

.workflow-detail__card-title {
  font-size: 15px;
  font-weight: 600;
}

.workflow-detail__card-count {
  margin-left: 10px;
  font-size: 13px;
  color: var(--el-text-color-secondary);
}

.workflow-detail__sim-tag {
  margin-left: 10px;
}

.workflow-detail__poll-tag {
  font-weight: normal;
}

.workflow-detail__mono {
  font-family: var(--el-font-family-mono, ui-monospace, SFMono-Regular, Menlo, monospace);
  font-size: 13px;
}

.workflow-detail__sha {
  word-break: break-all;
}

.workflow-detail__muted {
  color: var(--el-text-color-secondary);
  font-size: 12px;
}

.workflow-detail__filename {
  display: inline-block;
  max-width: 100%;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  vertical-align: bottom;
}

.workflow-detail__artifact-actions {
  display: flex;
  gap: 8px;
  margin-top: 12px;
}

.workflow-detail__alert {
  margin-bottom: 12px;
}

.workflow-detail__pagination {
  display: flex;
  justify-content: flex-end;
  margin-top: 16px;
}

.workflow-detail__hint {
  margin: 0;
  color: var(--el-text-color-regular);
}

.workflow-detail__error-actions {
  display: flex;
  gap: 8px;
  margin-top: 4px;
}
</style>
