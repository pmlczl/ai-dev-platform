<script setup lang="ts">
/**
 * The project management list.
 *
 * The page shows the projects of the backend and offers the operations of the
 * project aggregate: create, edit and delete. The state of the list - the
 * filters and the page - lives in the query of the URL, so a reload and the
 * buttons "back" and "forward" of the browser restore it.
 */
import { computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'

import PageState from '@/components/common/PageState.vue'
import ProjectFormDialog from '@/components/project/ProjectFormDialog.vue'
import ProjectSearchBar from '@/components/project/ProjectSearchBar.vue'
import ProjectTable from '@/components/project/ProjectTable.vue'
import { PROJECT_STATUS_VALUES } from '@/constants/status'
import { createProject, deleteProject, fetchProjects, updateProject } from '@/api/projects'
import { describeApiError } from '@/api/client'
import { useWorkspaceStore } from '@/stores'

import type { ProjectListItem, ProjectStatus } from '@/types'

/** The number of rows a page may show. */
const PAGE_SIZE_OPTIONS = [10, 20, 50, 100]
/** The number of rows a page shows by default. */
const DEFAULT_PAGE_SIZE = 20

/** The state of the list - it is mirrored in the query of the URL. */
interface QueryState {
  page: number
  page_size: number
  keyword: string
  status: ProjectStatus | ''
}

const route = useRoute()
const router = useRouter()
const workspace = useWorkspaceStore()

const projects = ref<ProjectListItem[]>([])
const total = ref(0)
const loading = ref(false)
const errorMessage = ref<string | null>(null)

/** The identifier of the project that is being deleted - it blocks a second one. */
const deletingId = ref<string | null>(null)
/** The dialog is open. */
const dialogVisible = ref(false)
/** The project that is edited - without it a new project is created. */
const editingProject = ref<ProjectListItem | null>(null)
/** The request of the dialog is running. */
const submitting = ref(false)

/** Read the state of the list out of the query of the URL. */
function readQuery(): QueryState {
  const raw = route.query
  const page = Number(raw.page)
  const pageSize = Number(raw.page_size)
  const keyword = typeof raw.keyword === 'string' ? raw.keyword : ''
  const status = typeof raw.status === 'string' ? raw.status : ''
  return {
    page: Number.isInteger(page) && page >= 1 ? page : 1,
    page_size: Number.isInteger(pageSize) && pageSize >= 1 && pageSize <= 100 ? pageSize : DEFAULT_PAGE_SIZE,
    keyword,
    status: PROJECT_STATUS_VALUES.includes(status as ProjectStatus)
      ? (status as ProjectStatus)
      : '',
  }
}

/** The state of the list that is currently applied. */
const query = computed(() => readQuery())

/**
 * The query that is written into the URL.
 *
 * A value that equals the default is left out, so the URL of the untouched
 * page stays clean.
 */
function buildQuery(state: QueryState): Record<string, string> {
  const result: Record<string, string> = {}
  if (state.page > 1) {
    result.page = String(state.page)
  }
  if (state.page_size !== DEFAULT_PAGE_SIZE) {
    result.page_size = String(state.page_size)
  }
  if (state.keyword) {
    result.keyword = state.keyword
  }
  if (state.status) {
    result.status = state.status
  }
  return result
}

/** True when two queries carry the same information. */
function sameQuery(left: Record<string, string>, right: Record<string, string>): boolean {
  const leftKeys = Object.keys(left)
  const rightKeys = Object.keys(right)
  if (leftKeys.length !== rightKeys.length) {
    return false
  }
  return leftKeys.every((key) => left[key] === right[key])
}

/** The state that is waiting to be written into the URL. */
let pendingState: QueryState | null = null
/** The handle of the scheduled write. */
let pendingFlush: Promise<void> | null = null

/**
 * Write the state of the list into the query of the URL.
 *
 * Several events of the pagination can arrive in the same tick - changing the
 * number of rows also moves the page. They are collected and written once, so
 * the history of the browser does not fill up with half finished states.
 */
function writeQuery(state: Partial<QueryState>): void {
  pendingState = { ...(pendingState ?? readQuery()), ...state }
  if (pendingFlush) {
    return
  }
  pendingFlush = Promise.resolve().then(() => {
    const next = pendingState as QueryState
    pendingState = null
    pendingFlush = null
    const query = buildQuery(next)
    if (sameQuery(query, buildQuery(readQuery()))) {
      return
    }
    void router.push({ path: route.path, query })
  })
}

/** Load the projects of the current page. */
async function loadProjects(): Promise<void> {
  const state = readQuery()
  loading.value = true
  errorMessage.value = null
  try {
    const page = await fetchProjects(
      {
        page: state.page,
        page_size: state.page_size,
        keyword: state.keyword || undefined,
        status: state.status || undefined,
      },
      // The page shows the failure itself - the toast would say it twice.
      { silent: true },
    )
    projects.value = page.items
    total.value = page.total
  } catch (error) {
    projects.value = []
    total.value = 0
    errorMessage.value = describeApiError(error)
  } finally {
    loading.value = false
  }
}

// The URL is the state of the page: every navigation loads the list again.
watch(
  () => route.query,
  () => {
    void loadProjects()
  },
  { immediate: true },
)

/** The user applied a filter. */
function handleSearch(payload: { keyword: string; status: ProjectStatus | '' }): void {
  writeQuery({ keyword: payload.keyword, status: payload.status, page: 1 })
}

/** The user asked for another page. */
function handlePageChange(page: number): void {
  writeQuery({ page })
}

/** The user asked for another number of rows. */
function handleSizeChange(pageSize: number): void {
  writeQuery({ page_size: pageSize, page: 1 })
}

/** Open the dialog for a new project. */
function openCreate(): void {
  editingProject.value = null
  dialogVisible.value = true
}

/** Open the dialog for an existing project. */
function openEdit(project: ProjectListItem): void {
  editingProject.value = project
  dialogVisible.value = true
}

/** Create or update the project of the dialog. */
async function handleSubmit(payload: {
  code: string
  name: string
  description: string | null
  status: ProjectStatus
  owner: string | null
}): Promise<void> {
  if (submitting.value) {
    return
  }
  submitting.value = true
  const editing = editingProject.value
  try {
    if (editing) {
      await updateProject(editing.id, {
        code: payload.code,
        name: payload.name,
        description: payload.description,
        status: payload.status,
        owner: payload.owner,
      })
      ElMessage.success('项目已更新')
    } else {
      await createProject({
        code: payload.code,
        name: payload.name,
        description: payload.description,
        status: payload.status,
        owner: payload.owner,
      })
      ElMessage.success('项目已创建')
    }
    dialogVisible.value = false
    editingProject.value = null
    // A new project belongs to the first page - it would be hidden otherwise.
    if (!editing && readQuery().page > 1) {
      writeQuery({ page: 1 })
    } else {
      await loadProjects()
    }
  } catch {
    // The interceptor of the client already told the user what went wrong.
  } finally {
    submitting.value = false
  }
}

/** Delete a project after the user confirmed the consequences. */
async function handleRemove(project: ProjectListItem): Promise<void> {
  if (deletingId.value !== null) {
    return
  }
  try {
    await ElMessageBox.confirm(
      `确定要删除项目「${project.name}」吗？` +
        `该项目下的 ${project.task_count} 个任务会被一并软删除；` +
        '项目、任务与审批记录仍保留在数据库中，但项目不再出现在列表里。',
      '删除项目',
      {
        type: 'warning',
        confirmButtonText: '删除',
        cancelButtonText: '取消',
        confirmButtonClass: 'el-button--danger',
      },
    )
  } catch {
    // The user cancelled the confirmation.
    return
  }

  deletingId.value = project.id
  try {
    await deleteProject(project.id)
    ElMessage.success('项目已删除')
    if (projects.value.length === 1 && readQuery().page > 1) {
      writeQuery({ page: readQuery().page - 1 })
    } else {
      await loadProjects()
    }
  } catch {
    // The interceptor of the client already told the user what went wrong.
  } finally {
    deletingId.value = null
  }
}

/** Open the details of a project. */
function handleView(project: ProjectListItem): void {
  workspace.focusProject(project.id)
  void router.push({ name: 'project-detail', params: { project_id: project.id } })
}
</script>

<template>
  <div class="project-list">
    <el-card shadow="never">
      <template #header>
        <div class="project-list__header">
          <div>
            <h2 class="project-list__title">项目管理</h2>
            <p class="project-list__subtitle">共 {{ total }} 个项目</p>
          </div>
          <el-button type="primary" @click="openCreate">
            <el-icon><Plus /></el-icon>
            <span>新建项目</span>
          </el-button>
        </div>
      </template>

      <ProjectSearchBar
        class="project-list__search"
        :keyword="query.keyword"
        :status="query.status"
        :loading="loading"
        @search="handleSearch"
        @refresh="loadProjects"
      />

      <PageState
        class="project-list__state"
        :loading="loading"
        :error="errorMessage"
        :empty="projects.length === 0"
        empty-text="没有符合条件的项目"
        min-height="240px"
      >
        <template #error>
          <el-button type="primary" plain @click="loadProjects">重试</el-button>
        </template>

        <template #empty>
          <el-button v-if="query.keyword || query.status" type="primary" plain @click="handleSearch({ keyword: '', status: '' })">
            清除筛选条件
          </el-button>
          <el-button v-else type="primary" @click="openCreate">新建项目</el-button>
        </template>

        <ProjectTable
          :projects="projects"
          :deleting-id="deletingId"
          @view="handleView"
          @edit="openEdit"
          @remove="handleRemove"
        />

        <div v-if="total > 0" class="project-list__pagination">
          <el-pagination
            background
            layout="total, sizes, prev, pager, next, jumper"
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

    <ProjectFormDialog
      v-model="dialogVisible"
      :project="editingProject"
      :submitting="submitting"
      @submit="handleSubmit"
    />
  </div>
</template>

<style scoped>
.project-list__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
}

.project-list__title {
  margin: 0;
  font-size: 18px;
  font-weight: 600;
}

.project-list__subtitle {
  margin: 4px 0 0;
  font-size: 13px;
  color: var(--el-text-color-secondary);
}

.project-list__search {
  margin-bottom: 16px;
}

.project-list__state {
  margin-top: 4px;
}

.project-list__pagination {
  display: flex;
  justify-content: flex-end;
  margin-top: 16px;
}
</style>
