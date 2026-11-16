<script setup lang="ts">
/**
 * The queue of the runs that wait for a human decision.
 *
 * The queue is a filtered view of the workflow runs: `GET /workflows` with
 * `status=waiting_approval`, which is the state the backend reaches when the
 * graph interrupts itself at the approval node. There is no separate
 * approval table behind this page, so a run that was decided elsewhere
 * leaves the queue as soon as the list is loaded again.
 *
 * The filters and the page live in the query of the URL, so a refresh
 * restores the same view. The list is loaded from the backend on every
 * entry; nothing of it is kept in a store.
 *
 * A queue is a shared view, and the platform cannot tell who looked at it,
 * so the page loads it again on a timer: a run decided by somebody else
 * disappears without a click. The timer stops when the page is left, and a
 * failed refresh is reported inline instead of replacing the rows the
 * approver is reading.
 */
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import ApprovalQueueTable from '@/components/approval/ApprovalQueueTable.vue'
import PageState from '@/components/common/PageState.vue'
import { describeApiError } from '@/api/client'
import { APPROVAL_QUEUE_POLL_INTERVAL_MS } from '@/constants/approval'
import { fetchProjects } from '@/api/projects'
import { fetchTasks } from '@/api/tasks'
import { fetchWorkflows } from '@/api/workflows'
import { useReferenceStore, useWorkspaceStore } from '@/stores'
import { formatDateTime } from '@/utils/format'

import type { ProjectRead, TaskRead, WorkflowRead } from '@/types'

const PAGE_SIZE_OPTIONS = [10, 20, 50]
const DEFAULT_PAGE_SIZE = 20
const OPTION_PAGE_SIZE = 100
/** The interval of the queue in the words of the toolbar. */
const AUTO_REFRESH_TEXT = `每 ${APPROVAL_QUEUE_POLL_INTERVAL_MS / 1000} 秒自动刷新 · `

const route = useRoute()
const router = useRouter()
const workspace = useWorkspaceStore()
const reference = useReferenceStore()

// --- the query ---------------------------------------------------------------------

interface ListQuery {
  page: number
  page_size: number
  project_id: string
  task_id: string
}

function readQuery(): ListQuery {
  const raw = route.query
  const page = Number(raw.page)
  const pageSize = Number(raw.page_size)
  return {
    page: Number.isInteger(page) && page >= 1 ? page : 1,
    page_size:
      Number.isInteger(pageSize) && PAGE_SIZE_OPTIONS.includes(pageSize)
        ? pageSize
        : DEFAULT_PAGE_SIZE,
    project_id: typeof raw.project_id === 'string' ? raw.project_id : '',
    task_id: typeof raw.task_id === 'string' ? raw.task_id : '',
  }
}

const query = computed(() => readQuery())

function writeQuery(patch: Partial<ListQuery>): void {
  const next = { ...readQuery(), ...patch }
  const result: Record<string, string> = {}
  if (next.page > 1) {
    result.page = String(next.page)
  }
  if (next.page_size !== DEFAULT_PAGE_SIZE) {
    result.page_size = String(next.page_size)
  }
  if (next.project_id) {
    result.project_id = next.project_id
  }
  if (next.task_id) {
    result.task_id = next.task_id
  }
  void router.push({ path: route.path, query: result })
}

const hasFilters = computed(
  () => Boolean(query.value.project_id || query.value.task_id),
)

function clearFilters(): void {
  writeQuery({ project_id: '', task_id: '', page: 1 })
}

// --- the filter options --------------------------------------------------------------

const projectOptions = ref<ProjectRead[]>([])
const projectOptionsLoading = ref(false)
const taskOptions = ref<TaskRead[]>([])
const taskOptionsLoading = ref(false)

async function loadProjectOptions(): Promise<void> {
  projectOptionsLoading.value = true
  try {
    const page = await fetchProjects({ page: 1, page_size: OPTION_PAGE_SIZE }, { silent: true })
    projectOptions.value = page.items
    reference.rememberProjects(page.items)
  } catch {
    // The filter stays usable by id; the list reports its own errors.
  } finally {
    projectOptionsLoading.value = false
  }
}

async function loadTaskOptions(projectId: string): Promise<void> {
  if (!projectId) {
    taskOptions.value = []
    return
  }
  taskOptionsLoading.value = true
  try {
    const page = await fetchTasks(
      { project_id: projectId, page: 1, page_size: OPTION_PAGE_SIZE },
      { silent: true },
    )
    taskOptions.value = page.items
    reference.rememberTasks(page.items)
  } catch {
    taskOptions.value = []
  } finally {
    taskOptionsLoading.value = false
  }
}

function handleProjectChange(projectId: string | null): void {
  // A new project invalidates the task filter.
  writeQuery({ project_id: projectId ?? '', task_id: '', page: 1 })
}

function handleTaskChange(taskId: string | null): void {
  writeQuery({ task_id: taskId ?? '', page: 1 })
}

const taskSelectOptions = computed<Array<{ value: string; label: string }>>(() => {
  const options = taskOptions.value.map((task) => ({
    value: task.id,
    label: `#${task.seq} ${task.title}`,
  }))
  const current = query.value.task_id
  if (current && !options.some((option) => option.value === current)) {
    const known = reference.tasks[current]
    options.unshift({
      value: current,
      label: known ? `#${known.seq} ${known.title}` : current.split('-')[0],
    })
  }
  return options
})

// --- the queue --------------------------------------------------------------------------

const workflows = ref<WorkflowRead[]>([])
const total = ref(0)
const loading = ref(false)
const error = ref<string | null>(null)
/** The error of a background refresh; the rows the approver reads stay. */
const pollError = ref<string | null>(null)
const refreshedAt = ref<string | null>(null)

let inflight: Promise<void> | null = null

/**
 * Load the queue.
 *
 * `background` marks the refresh of the timer: it must not clear the table
 * and it must not turn into the error state of the page, because the rows
 * that are already shown are the better guess at the truth than a blank.
 */
async function load(background = false): Promise<void> {
  if (inflight) {
    return inflight
  }
  if (!background) {
    loading.value = true
    error.value = null
  }
  inflight = (async () => {
    const state = readQuery()
    try {
      const page = await fetchWorkflows(
        {
          // The queue is exactly this state of the runs - the filter is not
          // a choice of the user.
          status: 'waiting_approval',
          page: state.page,
          page_size: state.page_size,
          project_id: state.project_id || undefined,
          task_id: state.task_id || undefined,
        },
        { silent: true },
      )
      workflows.value = page.items
      total.value = page.total
      refreshedAt.value = new Date().toISOString()
      pollError.value = null
      error.value = null
      await Promise.all([
        reference.resolveProjects([state.project_id, ...page.items.map((run) => run.project_id)]),
        reference.resolveTasks([state.task_id, ...page.items.map((run) => run.task_id)]),
      ])
    } catch (caught) {
      if (background) {
        pollError.value = describeApiError(caught)
      } else {
        workflows.value = []
        total.value = 0
        error.value = describeApiError(caught)
      }
    } finally {
      loading.value = false
      inflight = null
    }
  })()
  return inflight
}

// --- polling -------------------------------------------------------------------------------

/** Every run of this list waits for a person, so the list is always worth refreshing. */
const isQueueLive = computed(() => workflows.value.length > 0)

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
  if (unmounted || !isQueueLive.value) {
    return
  }
  pollTimer = window.setTimeout(async () => {
    pollTimer = null
    if (unmounted || route.name !== 'approvals') {
      return
    }
    await load(true)
    schedulePoll()
  }, APPROVAL_QUEUE_POLL_INTERVAL_MS)
}

watch(isQueueLive, () => schedulePoll())

onBeforeUnmount(() => {
  unmounted = true
  stopPolling()
})

// --- navigation ----------------------------------------------------------------------------

function handleDecide(workflow: WorkflowRead): void {
  workspace.focusWorkflow(workflow.id)
  void router.push({ name: 'approval-detail', params: { workflow_id: workflow.id } })
}

function handleViewWorkflow(workflow: WorkflowRead): void {
  workspace.focusWorkflow(workflow.id)
  void router.push({ name: 'workflow-detail', params: { workflow_id: workflow.id } })
}

function handleViewTask(taskId: string): void {
  workspace.focusTask(taskId)
  void router.push({ name: 'task-detail', params: { task_id: taskId } })
}

function gotoMonitoring(): void {
  void router.push({ name: 'workflows' })
}

// --- loading --------------------------------------------------------------------------------

void loadProjectOptions()

watch(
  () => query.value.project_id,
  (projectId) => {
    void loadTaskOptions(projectId)
  },
  { immediate: true },
)

watch(
  () => [route.query.page, route.query.page_size, route.query.project_id, route.query.task_id],
  async (next, previous) => {
    if (route.name !== 'approvals') {
      return
    }
    if (previous && next.every((value, index) => value === previous[index])) {
      return
    }
    await load()
    schedulePoll()
  },
  { immediate: true },
)
</script>

<template>
  <div class="approval-queue">
    <el-card shadow="never" class="approval-queue__card">
      <template #header>
        <div class="approval-queue__header">
          <div>
            <span class="approval-queue__title">待审批运行</span>
            <span class="approval-queue__count">共 {{ total }} 项等待决定</span>
          </div>
          <div class="approval-queue__toolbar">
            <span v-if="refreshedAt" class="approval-queue__refreshed">
              <template v-if="isQueueLive">{{ AUTO_REFRESH_TEXT }}</template>
              更新于 {{ formatDateTime(refreshedAt) }}
            </span>
            <el-button :loading="loading" @click="load()">
              <el-icon><Refresh /></el-icon>
              <span>刷新</span>
            </el-button>
          </div>
        </div>
      </template>

      <div class="approval-queue__filters">
        <el-select
          :model-value="query.project_id || null"
          placeholder="全部项目"
          clearable
          filterable
          :loading="projectOptionsLoading"
          style="width: 220px"
          @update:model-value="handleProjectChange"
        >
          <el-option
            v-for="project in projectOptions"
            :key="project.id"
            :label="`${project.code} ${project.name}`"
            :value="project.id"
          />
        </el-select>
        <el-select
          :model-value="query.task_id || null"
          :placeholder="query.project_id ? '全部任务' : '先选择项目'"
          clearable
          filterable
          :disabled="!query.project_id && taskSelectOptions.length === 0"
          :loading="taskOptionsLoading"
          style="width: 240px"
          @update:model-value="handleTaskChange"
        >
          <el-option
            v-for="option in taskSelectOptions"
            :key="option.value"
            :label="option.label"
            :value="option.value"
          />
        </el-select>
        <el-button v-if="hasFilters" text type="primary" @click="clearFilters">清除筛选</el-button>
      </div>

      <el-alert
        type="info"
        :closable="false"
        show-icon
        class="approval-queue__alert"
        title="列表来自工作流运行接口（状态为待审批），审批历史只追加不修改；平台当前没有登录与权限校验，任何打开页面的人都能提交决定，提交前请先确认该运行是否已由他人处理。"
      />

      <el-alert
        v-if="pollError"
        type="warning"
        :closable="false"
        show-icon
        class="approval-queue__alert"
        :title="`自动刷新失败，列表可能不是最新：${pollError}`"
      />

      <PageState
        :loading="loading && workflows.length === 0"
        :error="error"
        :empty="!loading && workflows.length === 0"
        :empty-text="hasFilters ? '没有符合条件的待审批运行' : '当前没有等待人工审批的运行'"
        min-height="240px"
      >
        <template #error>
          <el-button type="primary" plain @click="load()">重试</el-button>
        </template>
        <template #empty>
          <el-button v-if="hasFilters" type="primary" plain @click="clearFilters">
            清除筛选条件
          </el-button>
          <el-button v-else type="primary" plain @click="gotoMonitoring">前往工作流监控</el-button>
        </template>

        <ApprovalQueueTable
          :workflows="workflows"
          :projects="reference.projects"
          :tasks="reference.tasks"
          @decide="handleDecide"
          @view-workflow="handleViewWorkflow"
          @view-task="handleViewTask"
        />

        <div v-if="total > 0" class="approval-queue__pagination">
          <el-pagination
            background
            layout="total, sizes, prev, pager, next"
            :page-sizes="PAGE_SIZE_OPTIONS"
            :total="total"
            :current-page="query.page"
            :page-size="query.page_size"
            @current-change="(page: number) => writeQuery({ page })"
            @size-change="(size: number) => writeQuery({ page_size: size, page: 1 })"
          />
        </div>
      </PageState>
    </el-card>
  </div>
</template>

<style scoped>
.approval-queue__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  flex-wrap: wrap;
}

.approval-queue__title {
  font-size: 15px;
  font-weight: 600;
}

.approval-queue__count {
  margin-left: 10px;
  font-size: 13px;
  color: var(--el-text-color-secondary);
}

.approval-queue__toolbar {
  display: flex;
  align-items: center;
  gap: 12px;
}

.approval-queue__refreshed {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.approval-queue__filters {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  margin-bottom: 16px;
}

.approval-queue__alert {
  margin-bottom: 12px;
}

.approval-queue__pagination {
  display: flex;
  justify-content: flex-end;
  margin-top: 16px;
}
</style>
