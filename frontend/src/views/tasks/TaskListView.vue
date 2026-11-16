<script setup lang="ts">
/**
 * The list of every task of the platform.
 *
 * The page filters the tasks by project, status, priority and keyword; the
 * filters live in the query of the URL so a refresh restores the same list.
 * A task is created from the detail page of its project - the project is
 * the context of a task, and the form never asks for it.
 */
import { computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'

import PageState from '@/components/common/PageState.vue'
import TaskFormDialog from '@/components/task/TaskFormDialog.vue'
import TaskTable from '@/components/task/TaskTable.vue'
import { describeApiError } from '@/api/client'
import { fetchProjects } from '@/api/projects'
import { fetchTasks, updateTask } from '@/api/tasks'
import {
  PRIORITY_MAP,
  TASK_PRIORITY_VALUES,
  TASK_STATUS_VALUES,
  statusOptions,
} from '@/constants/status'
import { useReferenceStore, useWorkspaceStore } from '@/stores'

import type { TaskFormPayload } from '@/components/task/TaskFormDialog.vue'
import type { ProjectRead, TaskPriority, TaskRead, TaskStatus } from '@/types'

const PAGE_SIZE_OPTIONS = [10, 20, 50]
const DEFAULT_PAGE_SIZE = 20
const OPTION_PAGE_SIZE = 100

const TASK_STATUS_OPTIONS = statusOptions('task')
const TASK_PRIORITY_OPTIONS = TASK_PRIORITY_VALUES.map((value) => ({
  value,
  label: PRIORITY_MAP[value].label,
}))

const route = useRoute()
const router = useRouter()
const workspace = useWorkspaceStore()
const reference = useReferenceStore()

// --- the query ---------------------------------------------------------------------

interface ListQuery {
  page: number
  page_size: number
  project_id: string
  status: TaskStatus | ''
  priority: TaskPriority | ''
  keyword: string
}

function readQuery(): ListQuery {
  const raw = route.query
  const page = Number(raw.page)
  const pageSize = Number(raw.page_size)
  const status = typeof raw.status === 'string' ? raw.status : ''
  const priority = typeof raw.priority === 'string' ? raw.priority : ''
  return {
    page: Number.isInteger(page) && page >= 1 ? page : 1,
    page_size:
      Number.isInteger(pageSize) && PAGE_SIZE_OPTIONS.includes(pageSize)
        ? pageSize
        : DEFAULT_PAGE_SIZE,
    project_id: typeof raw.project_id === 'string' ? raw.project_id : '',
    status: TASK_STATUS_VALUES.includes(status as TaskStatus) ? (status as TaskStatus) : '',
    priority: TASK_PRIORITY_VALUES.includes(priority as TaskPriority)
      ? (priority as TaskPriority)
      : '',
    keyword: typeof raw.keyword === 'string' ? raw.keyword : '',
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
  if (next.status) {
    result.status = next.status
  }
  if (next.priority) {
    result.priority = next.priority
  }
  if (next.keyword) {
    result.keyword = next.keyword
  }
  void router.push({ path: route.path, query: result })
}

const keywordInput = ref(readQuery().keyword)

watch(
  () => query.value.keyword,
  (keyword) => {
    keywordInput.value = keyword
  },
)

const hasFilters = computed(() =>
  Boolean(query.value.project_id || query.value.status || query.value.priority || query.value.keyword),
)

// --- the filter options ---------------------------------------------------------------

const projectOptions = ref<ProjectRead[]>([])
const projectOptionsLoading = ref(false)

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

// --- the list --------------------------------------------------------------------------

const tasks = ref<TaskRead[]>([])
const total = ref(0)
const loading = ref(false)
const error = ref<string | null>(null)

async function load(): Promise<void> {
  const state = readQuery()
  loading.value = true
  error.value = null
  try {
    const page = await fetchTasks(
      {
        page: state.page,
        page_size: state.page_size,
        project_id: state.project_id || undefined,
        status: state.status || undefined,
        priority: state.priority || undefined,
        keyword: state.keyword || undefined,
      },
      { silent: true },
    )
    tasks.value = page.items
    total.value = page.total
    reference.rememberTasks(page.items)
  } catch (caught) {
    tasks.value = []
    total.value = 0
    error.value = describeApiError(caught)
  } finally {
    loading.value = false
  }
}

// --- the edit -----------------------------------------------------------------------------

const dialogVisible = ref(false)
const editingTask = ref<TaskRead | null>(null)
const submitting = ref(false)

function openEdit(task: TaskRead): void {
  editingTask.value = task
  dialogVisible.value = true
}

async function handleSubmit(payload: TaskFormPayload): Promise<void> {
  if (submitting.value || !editingTask.value) {
    return
  }
  submitting.value = true
  try {
    await updateTask(editingTask.value.id, payload)
    ElMessage.success('任务已更新')
    dialogVisible.value = false
    editingTask.value = null
    await load()
  } catch {
    // The interceptor of the client already told the user what went wrong.
  } finally {
    submitting.value = false
  }
}

// --- navigation ------------------------------------------------------------------------------

function handleView(task: TaskRead): void {
  workspace.focusTask(task.id)
  void router.push({ name: 'task-detail', params: { task_id: task.id } })
}

// --- loading ------------------------------------------------------------------------------------

void loadProjectOptions()

watch(
  () => [
    route.query.page,
    route.query.page_size,
    route.query.project_id,
    route.query.status,
    route.query.priority,
    route.query.keyword,
  ],
  (next, previous) => {
    if (route.name !== 'tasks') {
      return
    }
    if (previous && next.every((value, index) => value === previous[index])) {
      return
    }
    void load()
  },
  { immediate: true },
)
</script>

<template>
  <div class="task-list">
    <el-card shadow="never">
      <template #header>
        <div class="task-list__header">
          <div>
            <span class="task-list__title">任务管理</span>
            <span class="task-list__count">共 {{ total }} 个任务</span>
          </div>
          <div class="task-list__toolbar">
            <el-button :loading="loading" @click="load">
              <el-icon><Refresh /></el-icon>
              <span>刷新</span>
            </el-button>
            <el-tooltip content="任务在项目详情页中创建" placement="top">
              <el-button type="primary" @click="router.push({ name: 'projects' })">
                <el-icon><Plus /></el-icon>
                <span>前往项目新建任务</span>
              </el-button>
            </el-tooltip>
          </div>
        </div>
      </template>

      <div class="task-list__filters">
        <el-select
          :model-value="query.project_id || null"
          placeholder="全部项目"
          clearable
          filterable
          :loading="projectOptionsLoading"
          style="width: 220px"
          @update:model-value="(value: string | null) => writeQuery({ project_id: value ?? '', page: 1 })"
        >
          <el-option
            v-for="project in projectOptions"
            :key="project.id"
            :label="`${project.code} ${project.name}`"
            :value="project.id"
          />
        </el-select>
        <el-select
          :model-value="query.status || null"
          placeholder="全部状态"
          clearable
          style="width: 130px"
          @update:model-value="(value: TaskStatus | null) => writeQuery({ status: value ?? '', page: 1 })"
        >
          <el-option
            v-for="option in TASK_STATUS_OPTIONS"
            :key="option.value"
            :label="option.label"
            :value="option.value"
          />
        </el-select>
        <el-select
          :model-value="query.priority || null"
          placeholder="全部优先级"
          clearable
          style="width: 130px"
          @update:model-value="(value: TaskPriority | null) => writeQuery({ priority: value ?? '', page: 1 })"
        >
          <el-option
            v-for="option in TASK_PRIORITY_OPTIONS"
            :key="option.value"
            :label="option.label"
            :value="option.value"
          />
        </el-select>
        <el-input
          v-model="keywordInput"
          placeholder="搜索任务名称"
          clearable
          style="width: 220px"
          @keyup.enter="writeQuery({ keyword: keywordInput.trim(), page: 1 })"
          @clear="writeQuery({ keyword: '', page: 1 })"
        >
          <template #append>
            <el-button @click="writeQuery({ keyword: keywordInput.trim(), page: 1 })">
              <el-icon><Search /></el-icon>
            </el-button>
          </template>
        </el-input>
        <el-button
          v-if="hasFilters"
          text
          type="primary"
          @click="writeQuery({ project_id: '', status: '', priority: '', keyword: '', page: 1 })"
        >
          清除筛选
        </el-button>
      </div>

      <PageState
        :loading="loading"
        :error="error"
        :empty="tasks.length === 0"
        :empty-text="hasFilters ? '没有符合条件的任务' : '还没有任务，请先在项目详情页新建任务'"
        min-height="240px"
      >
        <template #error>
          <el-button type="primary" plain @click="load">重试</el-button>
        </template>

        <TaskTable :tasks="tasks" hide-workflow @view="handleView" @edit="openEdit" />

        <div v-if="total > 0" class="task-list__pagination">
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

    <TaskFormDialog
      v-model="dialogVisible"
      :task="editingTask"
      :submitting="submitting"
      @submit="handleSubmit"
    />
  </div>
</template>

<style scoped>
.task-list__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  flex-wrap: wrap;
}

.task-list__title {
  font-size: 15px;
  font-weight: 600;
}

.task-list__count {
  margin-left: 10px;
  font-size: 13px;
  color: var(--el-text-color-secondary);
}

.task-list__toolbar {
  display: flex;
  align-items: center;
  gap: 8px;
}

.task-list__filters {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  margin-bottom: 16px;
}

.task-list__pagination {
  display: flex;
  justify-content: flex-end;
  margin-top: 16px;
}
</style>
