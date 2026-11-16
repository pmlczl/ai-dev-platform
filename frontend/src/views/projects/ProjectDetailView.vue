<script setup lang="ts">
/**
 * The detail page of a project.
 *
 * The page shows the project itself, the tasks that belong to it and the
 * workflow runs of those tasks. Everything is loaded from the backend when
 * the page opens - the workspace store only remembers which project is open,
 * it is never the source of the data.
 *
 * The runs of the project are loaded with one request and grouped by task in
 * the browser; the table of the tasks shows the latest run of every task.
 */
import { computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'

import PageHeader from '@/components/common/PageHeader.vue'
import PageState from '@/components/common/PageState.vue'
import StatusTag from '@/components/common/StatusTag.vue'
import ProjectFormDialog from '@/components/project/ProjectFormDialog.vue'
import TaskFormDialog from '@/components/task/TaskFormDialog.vue'
import TaskTable from '@/components/task/TaskTable.vue'
import WorkflowTable from '@/components/workflow/WorkflowTable.vue'
import { describeApiError, isNotFoundError } from '@/api/client'
import { fetchProject, fetchProjectTasks, updateProject } from '@/api/projects'
import { createTask, updateTask } from '@/api/tasks'
import { fetchWorkflows } from '@/api/workflows'
import { TASK_STATUS_VALUES, statusOptions } from '@/constants/status'
import { useReferenceStore, useWorkspaceStore } from '@/stores'
import { formatDateTime } from '@/utils/format'

import type { TaskFormPayload } from '@/components/task/TaskFormDialog.vue'
import type { ProjectRead, ProjectStatus, TaskRead, TaskStatus, WorkflowRead } from '@/types'

const PAGE_SIZE_OPTIONS = [10, 20, 50]
const DEFAULT_PAGE_SIZE = 10
/** The runs of a project are loaded in one request - the backend caps a page at 100. */
const WORKFLOW_PAGE_SIZE = 100

const TASK_STATUS_OPTIONS = statusOptions('task')

const route = useRoute()
const router = useRouter()
const workspace = useWorkspaceStore()
const reference = useReferenceStore()

const projectId = computed(() => String(route.params.project_id ?? ''))

// --- the project -----------------------------------------------------------

const project = ref<ProjectRead | null>(null)
const projectLoading = ref(false)
const projectError = ref<string | null>(null)
/** The backend answered 404: the project does not exist or was soft deleted. */
const projectMissing = ref(false)

const projectDialogVisible = ref(false)
const projectSubmitting = ref(false)

async function loadProject(): Promise<void> {
  projectLoading.value = true
  projectError.value = null
  projectMissing.value = false
  try {
    const loaded = await fetchProject(projectId.value, { silent: true })
    project.value = loaded
    reference.rememberProjects([loaded])
    workspace.focusProject(loaded.id)
    workspace.project = loaded
  } catch (error) {
    project.value = null
    if (isNotFoundError(error)) {
      projectMissing.value = true
    }
    projectError.value = describeApiError(error)
  } finally {
    projectLoading.value = false
  }
}

async function handleProjectSubmit(payload: {
  code: string
  name: string
  description: string | null
  status: ProjectStatus
  owner: string | null
}): Promise<void> {
  if (projectSubmitting.value || !project.value) {
    return
  }
  projectSubmitting.value = true
  try {
    const updated = await updateProject(project.value.id, payload)
    project.value = updated
    reference.rememberProjects([updated])
    workspace.project = updated
    projectDialogVisible.value = false
    ElMessage.success('项目已更新')
  } catch {
    // The interceptor of the client already told the user what went wrong.
  } finally {
    projectSubmitting.value = false
  }
}

// --- the tasks ---------------------------------------------------------------

interface TaskQuery {
  page: number
  page_size: number
  status: TaskStatus | ''
}

const tasks = ref<TaskRead[]>([])
const tasksTotal = ref(0)
const tasksLoading = ref(false)
const tasksError = ref<string | null>(null)

const taskDialogVisible = ref(false)
const editingTask = ref<TaskRead | null>(null)
const taskSubmitting = ref(false)

/** The state of the task list is mirrored in the query of the URL. */
function readTaskQuery(): TaskQuery {
  const raw = route.query
  const page = Number(raw.task_page)
  const pageSize = Number(raw.task_page_size)
  const status = typeof raw.task_status === 'string' ? raw.task_status : ''
  return {
    page: Number.isInteger(page) && page >= 1 ? page : 1,
    page_size:
      Number.isInteger(pageSize) && PAGE_SIZE_OPTIONS.includes(pageSize)
        ? pageSize
        : DEFAULT_PAGE_SIZE,
    status: TASK_STATUS_VALUES.includes(status as TaskStatus) ? (status as TaskStatus) : '',
  }
}

const taskQuery = computed(() => readTaskQuery())

function writeTaskQuery(patch: Partial<TaskQuery>): void {
  const next = { ...readTaskQuery(), ...patch }
  const query: Record<string, string> = {}
  if (next.page > 1) {
    query.task_page = String(next.page)
  }
  if (next.page_size !== DEFAULT_PAGE_SIZE) {
    query.task_page_size = String(next.page_size)
  }
  if (next.status) {
    query.task_status = next.status
  }
  void router.push({ path: route.path, query })
}

async function loadTasks(): Promise<void> {
  const state = readTaskQuery()
  tasksLoading.value = true
  tasksError.value = null
  try {
    const page = await fetchProjectTasks(
      projectId.value,
      {
        page: state.page,
        page_size: state.page_size,
        status: state.status || undefined,
      },
      { silent: true },
    )
    tasks.value = page.items
    tasksTotal.value = page.total
    reference.rememberTasks(page.items)
  } catch (error) {
    tasks.value = []
    tasksTotal.value = 0
    tasksError.value = describeApiError(error)
  } finally {
    tasksLoading.value = false
  }
}

function handleTaskStatusChange(status: TaskStatus | ''): void {
  writeTaskQuery({ status, page: 1 })
}

function handleTaskPageChange(page: number): void {
  writeTaskQuery({ page })
}

function handleTaskSizeChange(pageSize: number): void {
  writeTaskQuery({ page_size: pageSize, page: 1 })
}

function openCreateTask(): void {
  editingTask.value = null
  taskDialogVisible.value = true
}

function openEditTask(task: TaskRead): void {
  editingTask.value = task
  taskDialogVisible.value = true
}

async function handleTaskSubmit(payload: TaskFormPayload): Promise<void> {
  if (taskSubmitting.value || !project.value) {
    return
  }
  taskSubmitting.value = true
  const editing = editingTask.value
  try {
    if (editing) {
      await updateTask(editing.id, payload)
      ElMessage.success('任务已更新')
    } else {
      // The project is the one of the page - the form never asks for it.
      await createTask({ project_id: project.value.id, ...payload })
      ElMessage.success('任务已创建')
    }
    taskDialogVisible.value = false
    editingTask.value = null
    const current = readTaskQuery()
    if (!editing && (current.page > 1 || current.status)) {
      // A new task must be visible: it belongs to the first page, and a
      // status filter would hide it.
      writeTaskQuery({ page: 1, status: '' })
    } else {
      await loadTasks()
    }
  } catch {
    // The interceptor of the client already told the user what went wrong.
  } finally {
    taskSubmitting.value = false
  }
}

function handleViewTask(task: TaskRead): void {
  workspace.focusTask(task.id)
  void router.push({ name: 'task-detail', params: { task_id: task.id } })
}

// --- the workflow runs ------------------------------------------------------

const workflows = ref<WorkflowRead[]>([])
const workflowsTotal = ref(0)
const workflowsLoading = ref(false)
const workflowsError = ref<string | null>(null)

/**
 * The latest run of every task.
 *
 * The backend lists the runs newest first, so the first run of a task that is
 * met is its latest one.
 */
const latestWorkflowByTask = computed<Record<string, WorkflowRead>>(() => {
  const result: Record<string, WorkflowRead> = {}
  for (const run of workflows.value) {
    if (run.task_id && !result[run.task_id]) {
      result[run.task_id] = run
    }
  }
  return result
})

/** The number of tasks that have at least one run. */
const tasksWithRuns = computed(() => Object.keys(latestWorkflowByTask.value).length)

async function loadWorkflows(): Promise<void> {
  workflowsLoading.value = true
  workflowsError.value = null
  try {
    const page = await fetchWorkflows(
      { project_id: projectId.value, page: 1, page_size: WORKFLOW_PAGE_SIZE },
      { silent: true },
    )
    workflows.value = page.items
    workflowsTotal.value = page.total
    // The names of the tasks of the runs: most of them are on the task page
    // already, the rest is fetched once and cached.
    await reference.resolveTasks(page.items.map((run) => run.task_id))
  } catch (error) {
    workflows.value = []
    workflowsTotal.value = 0
    workflowsError.value = describeApiError(error)
  } finally {
    workflowsLoading.value = false
  }
}

function handleViewWorkflow(workflow: WorkflowRead): void {
  workspace.focusWorkflow(workflow.id)
  void router.push({ name: 'workflow-detail', params: { workflow_id: workflow.id } })
}

function handleViewTaskById(taskId: string): void {
  workspace.focusTask(taskId)
  void router.push({ name: 'task-detail', params: { task_id: taskId } })
}

// --- loading --------------------------------------------------------------------

/** Load everything of the page again. */
async function reloadAll(): Promise<void> {
  await loadProject()
  if (project.value) {
    await Promise.all([loadTasks(), loadWorkflows()])
  }
}

// A new project id loads the whole page; a new task query loads the tasks only.
watch(
  projectId,
  () => {
    if (route.name !== 'project-detail') {
      return
    }
    void reloadAll()
  },
  { immediate: true },
)

watch(
  () => [route.query.task_page, route.query.task_page_size, route.query.task_status],
  (next, previous) => {
    if (route.name !== 'project-detail' || !project.value) {
      return
    }
    if (previous && next.every((value, index) => value === previous[index])) {
      return
    }
    void loadTasks()
  },
)
</script>

<template>
  <div class="project-detail">
    <PageState
      v-if="projectLoading || projectError"
      :loading="projectLoading"
      :error="projectError"
      loading-text="正在加载项目…"
      min-height="320px"
    >
      <template #error>
        <p v-if="projectMissing" class="project-detail__hint">
          该项目不存在或已被删除。
        </p>
        <div class="project-detail__error-actions">
          <el-button @click="router.push({ name: 'projects' })">返回项目列表</el-button>
          <el-button v-if="!projectMissing" type="primary" plain @click="reloadAll">重试</el-button>
        </div>
      </template>
    </PageState>

    <template v-else-if="project">
      <PageHeader
        :title="project.name"
        :subtitle="project.code"
        :back-to="{ name: 'projects' }"
        back-text="项目列表"
      >
        <template #tags>
          <StatusTag :status="project.status" kind="project" />
        </template>
        <template #actions>
          <el-button :loading="projectLoading" @click="reloadAll">
            <el-icon><Refresh /></el-icon>
            <span>刷新</span>
          </el-button>
          <el-button type="primary" @click="projectDialogVisible = true">
            <el-icon><Edit /></el-icon>
            <span>编辑项目</span>
          </el-button>
        </template>
      </PageHeader>

      <el-card shadow="never" class="project-detail__card">
        <template #header>
          <span class="project-detail__card-title">基本信息</span>
        </template>
        <el-descriptions :column="3" border size="default">
          <el-descriptions-item label="项目编号">
            <span class="project-detail__mono">{{ project.code }}</span>
          </el-descriptions-item>
          <el-descriptions-item label="项目名称">{{ project.name }}</el-descriptions-item>
          <el-descriptions-item label="状态">
            <StatusTag :status="project.status" kind="project" />
          </el-descriptions-item>
          <el-descriptions-item label="负责人">{{ project.owner || '—' }}</el-descriptions-item>
          <el-descriptions-item label="创建时间">
            {{ formatDateTime(project.created_at) }}
          </el-descriptions-item>
          <el-descriptions-item label="更新时间">
            {{ formatDateTime(project.updated_at) }}
          </el-descriptions-item>
          <el-descriptions-item label="项目描述" :span="3">
            <span class="project-detail__description">{{ project.description || '—' }}</span>
          </el-descriptions-item>
        </el-descriptions>
      </el-card>

      <el-card shadow="never" class="project-detail__card">
        <template #header>
          <div class="project-detail__card-header">
            <div>
              <span class="project-detail__card-title">任务列表</span>
              <span class="project-detail__card-count">共 {{ tasksTotal }} 个任务</span>
            </div>
            <div class="project-detail__toolbar">
              <el-select
                :model-value="taskQuery.status"
                placeholder="全部状态"
                clearable
                style="width: 140px"
                @update:model-value="handleTaskStatusChange"
              >
                <el-option
                  v-for="option in TASK_STATUS_OPTIONS"
                  :key="option.value"
                  :label="option.label"
                  :value="option.value"
                />
              </el-select>
              <el-button :loading="tasksLoading" @click="loadTasks">刷新</el-button>
              <el-button type="primary" @click="openCreateTask">
                <el-icon><Plus /></el-icon>
                <span>新建任务</span>
              </el-button>
            </div>
          </div>
        </template>

        <PageState
          :loading="tasksLoading"
          :error="tasksError"
          :empty="tasks.length === 0"
          empty-text="该项目下还没有任务"
          min-height="200px"
        >
          <template #error>
            <el-button type="primary" plain @click="loadTasks">重试</el-button>
          </template>
          <template #empty>
            <el-button
              v-if="taskQuery.status"
              type="primary"
              plain
              @click="handleTaskStatusChange('')"
            >
              清除筛选条件
            </el-button>
            <el-button v-else type="primary" @click="openCreateTask">新建任务</el-button>
          </template>

          <TaskTable
            :tasks="tasks"
            :workflows="latestWorkflowByTask"
            hide-project
            @view="handleViewTask"
            @edit="openEditTask"
            @view-workflow="handleViewWorkflow"
          />

          <div v-if="tasksTotal > 0" class="project-detail__pagination">
            <el-pagination
              background
              layout="total, sizes, prev, pager, next"
              :page-sizes="PAGE_SIZE_OPTIONS"
              :total="tasksTotal"
              :current-page="taskQuery.page"
              :page-size="taskQuery.page_size"
              @current-change="handleTaskPageChange"
              @size-change="handleTaskSizeChange"
            />
          </div>
        </PageState>
      </el-card>

      <el-card shadow="never" class="project-detail__card">
        <template #header>
          <div class="project-detail__card-header">
            <div>
              <span class="project-detail__card-title">工作流概览</span>
              <span class="project-detail__card-count">
                共 {{ workflowsTotal }} 次运行 · {{ tasksWithRuns }} 个任务已启动
              </span>
            </div>
            <div class="project-detail__toolbar">
              <el-button :loading="workflowsLoading" @click="loadWorkflows">刷新</el-button>
              <el-button @click="router.push({ name: 'workflows', query: { project_id: project.id } })">
                前往工作流监控
              </el-button>
            </div>
          </div>
        </template>

        <el-alert
          v-if="workflowsTotal > WORKFLOW_PAGE_SIZE"
          type="info"
          :closable="false"
          show-icon
          class="project-detail__alert"
          :title="`仅显示最近 ${WORKFLOW_PAGE_SIZE} 次运行，完整列表请前往工作流监控页`"
        />

        <PageState
          :loading="workflowsLoading"
          :error="workflowsError"
          :empty="workflows.length === 0"
          empty-text="该项目下还没有工作流运行记录，可在任务详情页启动工作流"
          min-height="160px"
        >
          <template #error>
            <el-button type="primary" plain @click="loadWorkflows">重试</el-button>
          </template>

          <WorkflowTable
            :workflows="workflows"
            :tasks="reference.tasks"
            :show-project="false"
            @view="handleViewWorkflow"
            @view-task="handleViewTaskById"
          />
        </PageState>
      </el-card>

      <el-card shadow="never" class="project-detail__card">
        <template #header>
          <span class="project-detail__card-title">GitLab 仓库</span>
        </template>
        <div class="project-detail__placeholder">
          <el-icon class="project-detail__placeholder-icon"><Connection /></el-icon>
          <span>GitLab仓库接入功能开发中</span>
        </div>
      </el-card>

      <ProjectFormDialog
        v-model="projectDialogVisible"
        :project="project"
        :submitting="projectSubmitting"
        @submit="handleProjectSubmit"
      />

      <TaskFormDialog
        v-model="taskDialogVisible"
        :task="editingTask"
        :submitting="taskSubmitting"
        @submit="handleTaskSubmit"
      />
    </template>
  </div>
</template>

<style scoped>
.project-detail__card {
  margin-bottom: 16px;
}

.project-detail__card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  flex-wrap: wrap;
}

.project-detail__card-title {
  font-size: 15px;
  font-weight: 600;
}

.project-detail__card-count {
  margin-left: 10px;
  font-size: 13px;
  color: var(--el-text-color-secondary);
}

.project-detail__toolbar {
  display: flex;
  align-items: center;
  gap: 8px;
}

.project-detail__mono {
  font-family: var(--el-font-family-mono, ui-monospace, SFMono-Regular, Menlo, monospace);
}

.project-detail__description {
  white-space: pre-wrap;
  word-break: break-word;
}

.project-detail__pagination {
  display: flex;
  justify-content: flex-end;
  margin-top: 16px;
}

.project-detail__alert {
  margin-bottom: 12px;
}

.project-detail__placeholder {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  min-height: 72px;
  color: var(--el-text-color-secondary);
}

.project-detail__placeholder-icon {
  font-size: 18px;
}

.project-detail__hint {
  margin: 0;
  color: var(--el-text-color-regular);
}

.project-detail__error-actions {
  display: flex;
  gap: 8px;
  margin-top: 4px;
}
</style>
