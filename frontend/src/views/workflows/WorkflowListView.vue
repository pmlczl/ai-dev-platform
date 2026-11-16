<script setup lang="ts">
/**
 * The monitoring of the workflow runs.
 *
 * The page lists every run of the platform, newest first, filtered by
 * project, task and status. The filters live in the query of the URL, so a
 * refresh of the browser restores the same list.
 *
 * While a run of the page is still going the list is polled - with one
 * request at a time, and never after the page was left.
 */
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import PageState from '@/components/common/PageState.vue'
import WorkflowTable from '@/components/workflow/WorkflowTable.vue'
import { describeApiError } from '@/api/client'
import { fetchProjects } from '@/api/projects'
import { fetchTasks } from '@/api/tasks'
import { fetchWorkflows } from '@/api/workflows'
import { WORKFLOW_STATUS_VALUES, statusOptions } from '@/constants/status'
import { WORKFLOW_POLL_INTERVAL_MS, isWorkflowLive } from '@/constants/workflow'
import { useReferenceStore, useWorkspaceStore } from '@/stores'
import { formatDateTime } from '@/utils/format'

import type { ProjectRead, TaskRead, WorkflowRead, WorkflowStatus } from '@/types'

const PAGE_SIZE_OPTIONS = [10, 20, 50]
const DEFAULT_PAGE_SIZE = 20
/** The options of the filters are loaded in one request - the backend caps a page at 100. */
const OPTION_PAGE_SIZE = 100

const WORKFLOW_STATUS_OPTIONS = statusOptions('workflow')

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
  status: WorkflowStatus | ''
}

function readQuery(): ListQuery {
  const raw = route.query
  const page = Number(raw.page)
  const pageSize = Number(raw.page_size)
  const status = typeof raw.status === 'string' ? raw.status : ''
  return {
    page: Number.isInteger(page) && page >= 1 ? page : 1,
    page_size:
      Number.isInteger(pageSize) && PAGE_SIZE_OPTIONS.includes(pageSize)
        ? pageSize
        : DEFAULT_PAGE_SIZE,
    project_id: typeof raw.project_id === 'string' ? raw.project_id : '',
    task_id: typeof raw.task_id === 'string' ? raw.task_id : '',
    status: WORKFLOW_STATUS_VALUES.includes(status as WorkflowStatus)
      ? (status as WorkflowStatus)
      : '',
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
  if (next.status) {
    result.status = next.status
  }
  void router.push({ path: route.path, query: result })
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
    // The filter stays usable by id; the list itself reports its own errors.
  } finally {
    projectOptionsLoading.value = false
  }
}

/** The tasks of the chosen project - without a project the task filter is the id of the URL only. */
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

/** The options of the task filter - the task of the URL is always offered. */
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

function handleProjectChange(projectId: string | null): void {
  // A new project invalidates the task filter.
  writeQuery({ project_id: projectId ?? '', task_id: '', page: 1 })
}

function handleTaskChange(taskId: string | null): void {
  writeQuery({ task_id: taskId ?? '', page: 1 })
}

function handleStatusChange(status: WorkflowStatus | '' | null): void {
  writeQuery({ status: status ?? '', page: 1 })
}

function handlePageChange(page: number): void {
  writeQuery({ page })
}

function handleSizeChange(pageSize: number): void {
  writeQuery({ page_size: pageSize, page: 1 })
}

function clearFilters(): void {
  writeQuery({ project_id: '', task_id: '', status: '', page: 1 })
}

const hasFilters = computed(
  () => Boolean(query.value.project_id || query.value.task_id || query.value.status),
)

// --- the list --------------------------------------------------------------------------

const workflows = ref<WorkflowRead[]>([])
const total = ref(0)
const loading = ref(false)
const error = ref<string | null>(null)
/** The time of the last successful load - shown next to the polling hint. */
const refreshedAt = ref<string | null>(null)
/** The error of a poll - the list keeps its rows, the problem is shown inline. */
const pollError = ref<string | null>(null)

let inflight: Promise<void> | null = null

/**
 * Load the page of the list.
 *
 * `background` marks a poll: the rows stay on screen while the request runs
 * and a failure does not replace them.
 */
async function load(background = false): Promise<void> {
  if (inflight) {
    return inflight
  }
  const state = readQuery()
  if (!background) {
    loading.value = true
    error.value = null
  }
  inflight = (async () => {
    try {
      const page = await fetchWorkflows(
        {
          page: state.page,
          page_size: state.page_size,
          project_id: state.project_id || undefined,
          task_id: state.task_id || undefined,
          status: state.status || undefined,
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

// --- polling -----------------------------------------------------------------------------

const hasLiveRun = computed(() => workflows.value.some((run) => isWorkflowLive(run.status)))
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
  if (unmounted || !hasLiveRun.value) {
    return
  }
  pollTimer = window.setTimeout(async () => {
    pollTimer = null
    if (unmounted || route.name !== 'workflows') {
      return
    }
    await load(true)
    schedulePoll()
  }, WORKFLOW_POLL_INTERVAL_MS)
}

watch(hasLiveRun, () => schedulePoll())

onBeforeUnmount(() => {
  unmounted = true
  stopPolling()
})

// --- navigation ----------------------------------------------------------------------------

function handleView(workflow: WorkflowRead): void {
  workspace.focusWorkflow(workflow.id)
  void router.push({ name: 'workflow-detail', params: { workflow_id: workflow.id } })
}

function handleViewTask(taskId: string): void {
  workspace.focusTask(taskId)
  void router.push({ name: 'task-detail', params: { task_id: taskId } })
}

function handleViewProject(projectId: string): void {
  workspace.focusProject(projectId)
  void router.push({ name: 'project-detail', params: { project_id: projectId } })
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
  () => [
    route.query.page,
    route.query.page_size,
    route.query.project_id,
    route.query.task_id,
    route.query.status,
  ],
  async (next, previous) => {
    if (route.name !== 'workflows') {
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
  <div class="workflow-list">
    <el-card shadow="never" class="workflow-list__card">
      <template #header>
        <div class="workflow-list__header">
          <div>
            <span class="workflow-list__title">工作流监控</span>
            <span class="workflow-list__count">共 {{ total }} 次运行</span>
          </div>
          <div class="workflow-list__toolbar">
            <span v-if="refreshedAt" class="workflow-list__refreshed">
              <template v-if="hasLiveRun">每 {{ WORKFLOW_POLL_INTERVAL_MS / 1000 }} 秒自动刷新 · </template>
              更新于 {{ formatDateTime(refreshedAt) }}
            </span>
            <el-button :loading="loading" @click="load()">
              <el-icon><Refresh /></el-icon>
              <span>刷新</span>
            </el-button>
          </div>
        </div>
      </template>

      <div class="workflow-list__filters">
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
        <el-select
          :model-value="query.status || null"
          placeholder="全部状态"
          clearable
          style="width: 140px"
          @update:model-value="handleStatusChange"
        >
          <el-option
            v-for="option in WORKFLOW_STATUS_OPTIONS"
            :key="option.value"
            :label="option.label"
            :value="option.value"
          />
        </el-select>
        <el-button v-if="hasFilters" text type="primary" @click="clearFilters">清除筛选</el-button>
      </div>

      <el-alert
        v-if="pollError"
        type="warning"
        :closable="false"
        show-icon
        class="workflow-list__alert"
        :title="`自动刷新失败，列表可能不是最新：${pollError}`"
      />

      <PageState
        :loading="loading && workflows.length === 0"
        :error="error"
        :empty="!loading && workflows.length === 0"
        :empty-text="hasFilters ? '没有符合条件的工作流运行' : '还没有工作流运行记录，可在任务详情页启动工作流'"
        min-height="240px"
      >
        <template #error>
          <el-button type="primary" plain @click="load()">重试</el-button>
        </template>
        <template #empty>
          <el-button v-if="hasFilters" type="primary" plain @click="clearFilters">清除筛选条件</el-button>
        </template>

        <WorkflowTable
          :workflows="workflows"
          :projects="reference.projects"
          :tasks="reference.tasks"
          @view="handleView"
          @view-task="handleViewTask"
          @view-project="handleViewProject"
        />

        <div v-if="total > 0" class="workflow-list__pagination">
          <el-pagination
            background
            layout="total, sizes, prev, pager, next"
            :page-sizes="PAGE_SIZE_OPTIONS"
            :total="total"
            :current-page="query.page"
            :page-size="query.page_size"
            @current-change="handlePageChange"
            @size-change="handleSizeChange"
          />
        </div>
      </PageState>
    </el-card>
  </div>
</template>

<style scoped>
.workflow-list__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  flex-wrap: wrap;
}

.workflow-list__title {
  font-size: 15px;
  font-weight: 600;
}

.workflow-list__count {
  margin-left: 10px;
  font-size: 13px;
  color: var(--el-text-color-secondary);
}

.workflow-list__toolbar {
  display: flex;
  align-items: center;
  gap: 12px;
}

.workflow-list__refreshed {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.workflow-list__filters {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  margin-bottom: 16px;
}

.workflow-list__alert {
  margin-bottom: 12px;
}

.workflow-list__pagination {
  display: flex;
  justify-content: flex-end;
  margin-top: 16px;
}
</style>
