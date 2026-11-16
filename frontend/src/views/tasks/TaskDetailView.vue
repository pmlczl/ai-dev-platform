<script setup lang="ts">
/**
 * The detail page of a task.
 *
 * The page shows the task, the requirement documents that were uploaded for
 * it, the files its workflow runs produced and the runs themselves. Every
 * block is loaded from the backend when the page opens - the workspace store
 * only remembers which task is open.
 *
 * A workflow run is started here: the backend executes it and answers with
 * the run, and the page opens the monitoring of that run with the id the
 * backend sent.
 */
import { computed, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'

import ArtifactTable from '@/components/artifact/ArtifactTable.vue'
import PageHeader from '@/components/common/PageHeader.vue'
import PageState from '@/components/common/PageState.vue'
import StatusTag from '@/components/common/StatusTag.vue'
import TaskFormDialog from '@/components/task/TaskFormDialog.vue'
import WorkflowStartDialog from '@/components/workflow/WorkflowStartDialog.vue'
import WorkflowTable from '@/components/workflow/WorkflowTable.vue'
import { fetchTaskArtifacts, uploadArtifact } from '@/api/artifacts'
import {
  describeApiError,
  extractErrorDetail,
  isConflictError,
  isNotFoundError,
} from '@/api/client'
import { fetchTask, fetchTaskWorkflows, updateTask } from '@/api/tasks'
import { startWorkflow } from '@/api/workflows'
import {
  ARTIFACT_ACCEPT,
  ARTIFACT_ALLOWED_EXTENSIONS,
  ARTIFACT_MAX_SIZE_BYTES,
  ARTIFACT_STAGE_OPTIONS,
  isAllowedArtifactExtension,
} from '@/constants/artifact'
import { isWorkflowLive } from '@/constants/workflow'
import { useReferenceStore, useWorkspaceStore } from '@/stores'
import { saveArtifact } from '@/utils/download'
import { formatDateTime, formatFileSize } from '@/utils/format'

import type { TaskFormPayload } from '@/components/task/TaskFormDialog.vue'
import type {
  ArtifactRead,
  ArtifactStage,
  TaskRead,
  WorkflowRead,
  WorkflowStartRequest,
} from '@/types'

const PAGE_SIZE = 10
/** The runs of a task are few - one page covers the history. */
const WORKFLOW_PAGE_SIZE = 20

const route = useRoute()
const router = useRouter()
const workspace = useWorkspaceStore()
const reference = useReferenceStore()

const taskId = computed(() => String(route.params.task_id ?? ''))

// --- the task -----------------------------------------------------------------

const task = ref<TaskRead | null>(null)
const taskLoading = ref(false)
const taskError = ref<string | null>(null)
/** The backend answered 404: the task does not exist or was soft deleted. */
const taskMissing = ref(false)

const taskDialogVisible = ref(false)
const taskSubmitting = ref(false)

async function loadTask(): Promise<void> {
  taskLoading.value = true
  taskError.value = null
  taskMissing.value = false
  try {
    const loaded = await fetchTask(taskId.value, { silent: true })
    task.value = loaded
    reference.rememberTasks([loaded])
    workspace.focusTask(loaded.id)
    workspace.task = loaded
    workspace.focusProject(loaded.project_id)
  } catch (error) {
    task.value = null
    if (isNotFoundError(error)) {
      taskMissing.value = true
    }
    taskError.value = describeApiError(error)
  } finally {
    taskLoading.value = false
  }
}

async function handleTaskSubmit(payload: TaskFormPayload): Promise<void> {
  if (taskSubmitting.value || !task.value) {
    return
  }
  taskSubmitting.value = true
  try {
    const updated = await updateTask(task.value.id, payload)
    task.value = updated
    reference.rememberTasks([updated])
    workspace.task = updated
    taskDialogVisible.value = false
    ElMessage.success('任务已更新')
  } catch {
    // The interceptor of the client already told the user what went wrong.
  } finally {
    taskSubmitting.value = false
  }
}

function goToProject(): void {
  if (!task.value) {
    return
  }
  void router.push({ name: 'project-detail', params: { project_id: task.value.project_id } })
}

// --- the files ---------------------------------------------------------------------

/** One paged list of files - the requirement documents and the results use it. */
interface ArtifactList {
  items: ArtifactRead[]
  total: number
  page: number
  loading: boolean
  error: string | null
}

function emptyList(): ArtifactList {
  return { items: [], total: 0, page: 1, loading: false, error: null }
}

/** The requirement documents: the files of the `design` stage. */
const prd = reactive<ArtifactList>(emptyList())
/** The results: every file of the task, filtered by stage. */
const results = reactive<ArtifactList>(emptyList())
const resultsStage = ref<ArtifactStage | ''>('')

/** The ids of the files that are being downloaded. */
const downloading = reactive(new Set<string>())

async function loadList(
  list: ArtifactList,
  params: { stage?: ArtifactStage },
  page = list.page,
): Promise<void> {
  list.loading = true
  list.error = null
  try {
    const result = await fetchTaskArtifacts(
      taskId.value,
      { page, page_size: PAGE_SIZE, ...params },
      { silent: true },
    )
    list.items = result.items
    list.total = result.total
    list.page = result.page
  } catch (error) {
    list.items = []
    list.total = 0
    list.error = describeApiError(error)
  } finally {
    list.loading = false
  }
}

function loadPrd(page = prd.page): Promise<void> {
  return loadList(prd, { stage: 'design' }, page)
}

function loadResults(page = results.page): Promise<void> {
  return loadList(results, resultsStage.value ? { stage: resultsStage.value } : {}, page)
}

function handleResultsStageChange(stage: ArtifactStage | ''): void {
  resultsStage.value = stage
  void loadResults(1)
}

async function handleDownload(artifact: ArtifactRead): Promise<void> {
  if (downloading.has(artifact.id)) {
    return
  }
  downloading.add(artifact.id)
  try {
    await saveArtifact(artifact)
  } catch {
    // The interceptor of the client already told the user what went wrong.
  } finally {
    downloading.delete(artifact.id)
  }
}

// --- the upload -----------------------------------------------------------------------

const fileInput = ref<HTMLInputElement | null>(null)
const uploading = ref(false)
const uploadPercent = ref(0)
const uploadName = ref('')

const uploadHint = `支持 ${ARTIFACT_ALLOWED_EXTENSIONS.map((ext) => `.${ext}`).join(' ')}，单个文件不超过 ${formatFileSize(ARTIFACT_MAX_SIZE_BYTES)}；同名文件会生成新版本，旧版本标记为“已被替换”。`

function openFilePicker(): void {
  if (uploading.value) {
    return
  }
  fileInput.value?.click()
}

/** The checks of the backend, run before the upload so the user is told early. */
function validateFile(file: File): string | null {
  if (!isAllowedArtifactExtension(file.name)) {
    return `不允许上传该类型的文件，支持：${ARTIFACT_ALLOWED_EXTENSIONS.map((ext) => `.${ext}`).join(' ')}`
  }
  if (file.size > ARTIFACT_MAX_SIZE_BYTES) {
    return `文件过大（${formatFileSize(file.size)}），最大允许 ${formatFileSize(ARTIFACT_MAX_SIZE_BYTES)}`
  }
  if (file.size === 0) {
    return '不能上传空文件'
  }
  return null
}

async function handleFileChange(event: Event): Promise<void> {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  // The same file can be picked again after the input is reset.
  input.value = ''
  if (!file || uploading.value || !task.value) {
    return
  }
  const problem = validateFile(file)
  if (problem) {
    ElMessage.warning(problem)
    return
  }
  uploading.value = true
  uploadPercent.value = 0
  uploadName.value = file.name
  try {
    const created = await uploadArtifact(
      task.value.id,
      { file, stage: 'design' },
      (percent) => {
        uploadPercent.value = percent
      },
    )
    ElMessage.success(`已上传 ${file.name}（v${created.version}）`)
    await Promise.all([loadPrd(1), loadResults(1)])
  } catch (error) {
    ElMessage.error(describeApiError(error))
  } finally {
    uploading.value = false
    uploadPercent.value = 0
    uploadName.value = ''
  }
}

// --- the workflow runs ------------------------------------------------------------

const workflows = ref<WorkflowRead[]>([])
const workflowsTotal = ref(0)
const workflowsLoading = ref(false)
const workflowsError = ref<string | null>(null)

const startDialogVisible = ref(false)
const starting = ref(false)

/** The run of the task that is still going - at most one exists. */
const liveWorkflow = computed(
  () => workflows.value.find((run) => isWorkflowLive(run.status)) ?? null,
)

/**
 * Whether the task has ended.
 *
 * The backend refuses to start a workflow for a completed or cancelled task
 * (409); the page states the rule before the request is sent.
 */
const taskFinished = computed(
  () => task.value?.status === 'completed' || task.value?.status === 'cancelled',
)

/** The reason the workflow cannot be started, or null when it can. */
const startBlockedReason = computed<string | null>(() => {
  if (taskFinished.value) {
    return '任务已结束（已完成或已取消），不能再启动工作流。'
  }
  if (liveWorkflow.value) {
    return `当前有一次运行尚未结束（${liveWorkflow.value.id.split('-')[0]}），新的工作流要等它结束后才能启动。`
  }
  return null
})

async function loadWorkflows(): Promise<void> {
  workflowsLoading.value = true
  workflowsError.value = null
  try {
    const page = await fetchTaskWorkflows(
      taskId.value,
      { page: 1, page_size: WORKFLOW_PAGE_SIZE },
      { silent: true },
    )
    workflows.value = page.items
    workflowsTotal.value = page.total
  } catch (error) {
    workflows.value = []
    workflowsTotal.value = 0
    workflowsError.value = describeApiError(error)
  } finally {
    workflowsLoading.value = false
  }
}

function openWorkflow(workflowId: string): void {
  workspace.focusWorkflow(workflowId)
  void router.push({ name: 'workflow-detail', params: { workflow_id: workflowId } })
}

function handleViewWorkflow(workflow: WorkflowRead): void {
  openWorkflow(workflow.id)
}

function openStartDialog(): void {
  if (startBlockedReason.value) {
    // The backend refuses the run anyway; the page says so first.
    ElMessage.warning(startBlockedReason.value)
    return
  }
  startDialogVisible.value = true
}

async function handleStart(payload: WorkflowStartRequest): Promise<void> {
  if (starting.value || !task.value) {
    return
  }
  starting.value = true
  try {
    const run = await startWorkflow(task.value.id, payload)
    startDialogVisible.value = false
    ElMessage.success(`工作流已启动（ID ${run.id.split('-')[0]}），正在打开监控页`)
    openWorkflow(run.id)
  } catch (error) {
    if (isConflictError(error)) {
      const detail = extractErrorDetail<{ existing_workflow_id?: string }>(error)
      const existing = detail?.existing_workflow_id
      startDialogVisible.value = false
      // The page was stale: either a run exists or the task has ended since
      // it was loaded. Both are read again from the backend.
      await Promise.all([loadTask(), loadWorkflows()])
      if (existing) {
        try {
          await ElMessageBox.confirm(
            '该任务已有进行中的工作流，不能重复启动。是否前往查看？',
            '工作流已存在',
            { confirmButtonText: '前往查看', cancelButtonText: '留在本页', type: 'warning' },
          )
          openWorkflow(existing)
        } catch {
          // The user stays on the page.
        }
      }
    }
    // Every other failure was already reported by the interceptor of the client.
  } finally {
    starting.value = false
  }
}

// --- loading -----------------------------------------------------------------------------

/** Load everything of the page again. */
async function reloadAll(): Promise<void> {
  await loadTask()
  if (task.value) {
    await Promise.all([loadPrd(1), loadResults(1), loadWorkflows()])
  }
}

watch(
  taskId,
  () => {
    if (route.name !== 'task-detail') {
      return
    }
    prd.page = 1
    results.page = 1
    void reloadAll()
  },
  { immediate: true },
)
</script>

<template>
  <div class="task-detail">
    <PageState
      v-if="(taskLoading && !task) || taskError"
      :loading="taskLoading"
      :error="taskError"
      loading-text="正在加载任务…"
      min-height="320px"
    >
      <template #error>
        <p v-if="taskMissing" class="task-detail__hint">该任务不存在或已被删除。</p>
        <div class="task-detail__error-actions">
          <el-button @click="router.push({ name: 'projects' })">返回项目列表</el-button>
          <el-button v-if="!taskMissing" type="primary" plain @click="reloadAll">重试</el-button>
        </div>
      </template>
    </PageState>

    <template v-else-if="task">
      <PageHeader
        :title="task.title"
        :back-to="{ name: 'project-detail', params: { project_id: task.project_id } }"
        back-text="项目详情"
      >
        <template #subtitle>
          <span>任务 #{{ task.seq }}</span>
          <span v-if="task.project_code"> · {{ task.project_code }}</span>
          <span v-if="task.project_name"> {{ task.project_name }}</span>
        </template>
        <template #tags>
          <StatusTag :status="task.status" kind="task" />
          <StatusTag :status="task.priority" kind="priority" />
        </template>
        <template #actions>
          <el-button :loading="taskLoading" @click="reloadAll">
            <el-icon><Refresh /></el-icon>
            <span>刷新</span>
          </el-button>
          <el-button @click="taskDialogVisible = true">
            <el-icon><Edit /></el-icon>
            <span>编辑任务</span>
          </el-button>
          <el-button
            type="primary"
            :disabled="Boolean(startBlockedReason) || workflowsLoading"
            :loading="starting"
            @click="openStartDialog"
          >
            <el-icon><VideoPlay /></el-icon>
            <span>启动工作流</span>
          </el-button>
        </template>
      </PageHeader>

      <el-card shadow="never" class="task-detail__card">
        <template #header>
          <span class="task-detail__card-title">基本信息</span>
        </template>
        <el-descriptions :column="3" border size="default">
          <el-descriptions-item label="任务序号">#{{ task.seq }}</el-descriptions-item>
          <el-descriptions-item label="任务名称">{{ task.title }}</el-descriptions-item>
          <el-descriptions-item label="所属项目">
            <el-link type="primary" underline="never" @click="goToProject">
              {{ task.project_name || task.project_id }}
            </el-link>
            <span v-if="task.project_code" class="task-detail__muted"> ({{ task.project_code }})</span>
          </el-descriptions-item>
          <el-descriptions-item label="状态">
            <StatusTag :status="task.status" kind="task" />
          </el-descriptions-item>
          <el-descriptions-item label="优先级">
            <StatusTag :status="task.priority" kind="priority" />
          </el-descriptions-item>
          <el-descriptions-item label="负责人">{{ task.assignee || '—' }}</el-descriptions-item>
          <el-descriptions-item label="创建时间">{{ formatDateTime(task.created_at) }}</el-descriptions-item>
          <el-descriptions-item label="更新时间">{{ formatDateTime(task.updated_at) }}</el-descriptions-item>
          <el-descriptions-item label="任务 ID">
            <span class="task-detail__mono">{{ task.id }}</span>
          </el-descriptions-item>
          <el-descriptions-item label="任务描述" :span="3">
            <span class="task-detail__description">{{ task.description || '—' }}</span>
          </el-descriptions-item>
        </el-descriptions>
      </el-card>

      <el-card shadow="never" class="task-detail__card">
        <template #header>
          <div class="task-detail__card-header">
            <div>
              <span class="task-detail__card-title">需求文档（PRD）</span>
              <span class="task-detail__card-count">共 {{ prd.total }} 个文件</span>
            </div>
            <div class="task-detail__toolbar">
              <el-button :loading="prd.loading" @click="loadPrd()">刷新</el-button>
              <el-button type="primary" :loading="uploading" @click="openFilePicker">
                <el-icon><Upload /></el-icon>
                <span>上传文档</span>
              </el-button>
              <input
                ref="fileInput"
                class="task-detail__file-input"
                type="file"
                :accept="ARTIFACT_ACCEPT"
                @change="handleFileChange"
              />
            </div>
          </div>
        </template>

        <p class="task-detail__upload-hint">{{ uploadHint }}</p>

        <div v-if="uploading" class="task-detail__upload-progress">
          <span class="task-detail__upload-name" :title="uploadName">正在上传 {{ uploadName }}</span>
          <el-progress :percentage="uploadPercent" :stroke-width="8" />
        </div>

        <PageState
          :loading="prd.loading"
          :error="prd.error"
          :empty="prd.items.length === 0"
          empty-text="还没有上传需求文档"
          min-height="160px"
        >
          <template #error>
            <el-button type="primary" plain @click="loadPrd()">重试</el-button>
          </template>
          <ArtifactTable
            :artifacts="prd.items"
            :downloading="downloading"
            time-label="上传时间"
            @download="handleDownload"
          />
          <div v-if="prd.total > PAGE_SIZE" class="task-detail__pagination">
            <el-pagination
              background
              layout="total, prev, pager, next"
              :total="prd.total"
              :current-page="prd.page"
              :page-size="PAGE_SIZE"
              @current-change="(page: number) => loadPrd(page)"
            />
          </div>
        </PageState>
      </el-card>

      <el-card shadow="never" class="task-detail__card">
        <template #header>
          <div class="task-detail__card-header">
            <div>
              <span class="task-detail__card-title">研发成果</span>
              <span class="task-detail__card-count">共 {{ results.total }} 个文件</span>
            </div>
            <div class="task-detail__toolbar">
              <el-select
                :model-value="resultsStage"
                placeholder="全部阶段"
                clearable
                style="width: 130px"
                @update:model-value="handleResultsStageChange"
              >
                <el-option
                  v-for="option in ARTIFACT_STAGE_OPTIONS"
                  :key="option.value"
                  :label="option.label"
                  :value="option.value"
                />
              </el-select>
              <el-button :loading="results.loading" @click="loadResults()">刷新</el-button>
            </div>
          </div>
        </template>

        <el-alert
          type="info"
          :closable="false"
          show-icon
          class="task-detail__alert"
          title="标记为“模拟成果”的文件由本地模拟工作流按固定模板生成，不是真实 AI 模型的输出；“人工上传”的文件（含设计阶段的需求文档）也列在这里。"
        />

        <PageState
          :loading="results.loading"
          :error="results.error"
          :empty="results.items.length === 0"
          empty-text="还没有研发成果，启动工作流后会在这里生成"
          min-height="160px"
        >
          <template #error>
            <el-button type="primary" plain @click="loadResults()">重试</el-button>
          </template>
          <ArtifactTable
            :artifacts="results.items"
            :downloading="downloading"
            show-stage
            show-source
            @download="handleDownload"
          />
          <div v-if="results.total > PAGE_SIZE" class="task-detail__pagination">
            <el-pagination
              background
              layout="total, prev, pager, next"
              :total="results.total"
              :current-page="results.page"
              :page-size="PAGE_SIZE"
              @current-change="(page: number) => loadResults(page)"
            />
          </div>
        </PageState>
      </el-card>

      <el-card shadow="never" class="task-detail__card">
        <template #header>
          <div class="task-detail__card-header">
            <div>
              <span class="task-detail__card-title">工作流运行</span>
              <span class="task-detail__card-count">共 {{ workflowsTotal }} 次运行</span>
            </div>
            <div class="task-detail__toolbar">
              <el-button :loading="workflowsLoading" @click="loadWorkflows">刷新</el-button>
              <el-button @click="router.push({ name: 'workflows', query: { task_id: task.id } })">
                前往工作流监控
              </el-button>
            </div>
          </div>
        </template>

        <el-alert
          v-if="startBlockedReason"
          :type="liveWorkflow ? 'warning' : 'info'"
          :closable="false"
          show-icon
          class="task-detail__alert"
        >
          <template #title>
            <span>{{ startBlockedReason }}</span>
            <el-link
              v-if="liveWorkflow"
              type="primary"
              underline="never"
              class="task-detail__alert-link"
              @click="openWorkflow(liveWorkflow.id)"
            >
              查看该运行
            </el-link>
          </template>
        </el-alert>

        <PageState
          :loading="workflowsLoading"
          :error="workflowsError"
          :empty="workflows.length === 0"
          empty-text="该任务还没有工作流运行记录"
          min-height="160px"
        >
          <template #error>
            <el-button type="primary" plain @click="loadWorkflows">重试</el-button>
          </template>
          <template #empty>
            <el-button type="primary" :disabled="Boolean(startBlockedReason)" @click="openStartDialog">
              启动工作流
            </el-button>
          </template>
          <WorkflowTable
            :workflows="workflows"
            :show-project="false"
            :show-task="false"
            @view="handleViewWorkflow"
          />
          <p v-if="workflowsTotal > WORKFLOW_PAGE_SIZE" class="task-detail__muted task-detail__more">
            仅显示最近 {{ WORKFLOW_PAGE_SIZE }} 次运行，完整列表请前往工作流监控页。
          </p>
        </PageState>
      </el-card>

      <TaskFormDialog
        v-model="taskDialogVisible"
        :task="task"
        :submitting="taskSubmitting"
        @submit="handleTaskSubmit"
      />

      <WorkflowStartDialog
        v-model="startDialogVisible"
        :submitting="starting"
        :task-title="task.title"
        @submit="handleStart"
      />
    </template>
  </div>
</template>

<style scoped>
.task-detail__card {
  margin-bottom: 16px;
}

.task-detail__card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  flex-wrap: wrap;
}

.task-detail__card-title {
  font-size: 15px;
  font-weight: 600;
}

.task-detail__card-count {
  margin-left: 10px;
  font-size: 13px;
  color: var(--el-text-color-secondary);
}

.task-detail__toolbar {
  display: flex;
  align-items: center;
  gap: 8px;
}

.task-detail__file-input {
  display: none;
}

.task-detail__upload-hint {
  margin: 0 0 12px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.task-detail__upload-progress {
  margin-bottom: 12px;
}

.task-detail__upload-name {
  display: block;
  margin-bottom: 4px;
  font-size: 13px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.task-detail__mono {
  font-family: var(--el-font-family-mono, ui-monospace, SFMono-Regular, Menlo, monospace);
  font-size: 13px;
}

.task-detail__muted {
  color: var(--el-text-color-secondary);
  font-size: 13px;
}

.task-detail__more {
  margin: 12px 0 0;
}

.task-detail__description {
  white-space: pre-wrap;
  word-break: break-word;
}

.task-detail__pagination {
  display: flex;
  justify-content: flex-end;
  margin-top: 16px;
}

.task-detail__alert {
  margin-bottom: 12px;
}

.task-detail__alert-link {
  margin-left: 8px;
  vertical-align: baseline;
}

.task-detail__hint {
  margin: 0;
  color: var(--el-text-color-regular);
}

.task-detail__error-actions {
  display: flex;
  gap: 8px;
  margin-top: 4px;
}
</style>
