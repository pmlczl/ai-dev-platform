<script setup lang="ts">
/**
 * The table of the project list.
 *
 * The component only renders what the backend sent; every action is handed
 * back to the page, which owns the requests and the confirmations.
 */
import StatusTag from '@/components/common/StatusTag.vue'
import { formatDateTime } from '@/utils/format'

import type { ProjectListItem } from '@/types'
const props = withDefaults(
  defineProps<{
    /** The projects of the current page. */
    projects: ProjectListItem[]
    /** The identifier of the project that is being deleted, if any. */
    deletingId?: string | null
  }>(),
  { deletingId: null },
)

const emit = defineEmits<{
  /** The user opened the details of a project. */
  (event: 'view', project: ProjectListItem): void
  /** The user asked to edit a project. */
  (event: 'edit', project: ProjectListItem): void
  /** The user asked to delete a project. */
  (event: 'remove', project: ProjectListItem): void
}>()

/** True while the given project is being deleted. */
function isDeleting(project: ProjectListItem): boolean {
  return props.deletingId === project.id
}

/**
 * Split a timestamp into the date and the time of the day.
 *
 * The column shows both parts on their own line: a table row stays one line
 * high and the full timestamp is still readable.
 */
function splitDateTime(value: string): { date: string; time: string } {
  const [date, time = ''] = formatDateTime(value).split(' ')
  return { date, time }
}
</script>

<template>
  <el-table
    v-loading="deletingId !== null"
    class="project-table"
    :data="projects"
    row-key="id"
    stripe
    style="width: 100%"
  >
    <el-table-column label="项目名称" min-width="190">
      <template #default="{ row }: { row: ProjectListItem }">
        <el-link type="primary" class="project-table__name" @click="emit('view', row)">
          {{ row.name }}
        </el-link>
        <div class="project-table__code">{{ row.code }}</div>
      </template>
    </el-table-column>

    <el-table-column label="项目描述" min-width="150" show-overflow-tooltip>
      <template #default="{ row }: { row: ProjectListItem }">
        <span class="project-table__description">{{ row.description || '—' }}</span>
      </template>
    </el-table-column>

    <el-table-column label="状态" width="88" align="center">
      <template #default="{ row }: { row: ProjectListItem }">
        <StatusTag :status="row.status" kind="project" />
      </template>
    </el-table-column>

    <el-table-column label="Git 仓库" width="96" align="center">
      <template #default>
        <el-tooltip content="GitLab 仓库关联功能尚未提供，后端暂无关联字段" placement="top">
          <el-tag type="info" effect="plain" size="small">未关联</el-tag>
        </el-tooltip>
      </template>
    </el-table-column>

    <el-table-column label="任务数" width="76" align="center">
      <template #default="{ row }: { row: ProjectListItem }">
        {{ row.task_count }}
      </template>
    </el-table-column>

    <el-table-column label="创建时间" width="110">
      <template #default="{ row }: { row: ProjectListItem }">
        <div class="project-table__time">
          <span>{{ splitDateTime(row.created_at).date }}</span>
          <span class="project-table__time-part">{{ splitDateTime(row.created_at).time }}</span>
        </div>
      </template>
    </el-table-column>

    <el-table-column label="更新时间" width="110">
      <template #default="{ row }: { row: ProjectListItem }">
        <div class="project-table__time">
          <span>{{ splitDateTime(row.updated_at).date }}</span>
          <span class="project-table__time-part">{{ splitDateTime(row.updated_at).time }}</span>
        </div>
      </template>
    </el-table-column>

    <el-table-column label="操作" width="176" align="center" fixed="right">
      <template #default="{ row }: { row: ProjectListItem }">
        <el-button link type="primary" @click="emit('view', row)">详情</el-button>
        <el-button link type="primary" @click="emit('edit', row)">编辑</el-button>
        <el-button
          link
          type="danger"
          :loading="isDeleting(row)"
          :disabled="deletingId !== null && !isDeleting(row)"
          @click="emit('remove', row)"
        >
          删除
        </el-button>
      </template>
    </el-table-column>
  </el-table>
</template>

<style scoped>
.project-table__name {
  font-weight: 500;
}

.project-table__code {
  margin-top: 2px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.project-table__description {
  color: var(--el-text-color-regular);
}

.project-table__time {
  display: flex;
  flex-direction: column;
  line-height: 1.4;
}

.project-table__time-part {
  color: var(--el-text-color-secondary);
  font-size: 12px;
}
</style>
