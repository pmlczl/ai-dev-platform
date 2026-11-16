<script setup lang="ts">
/**
 * The table of the tasks of a project.
 *
 * The component renders what the backend sent. The workflow column shows the
 * latest run of a task when the page handed the runs over - the runs are
 * loaded once for the whole project, never one request per row.
 */
import StatusTag from '@/components/common/StatusTag.vue'
import { formatDateTime } from '@/utils/format'

import type { TaskRead, WorkflowRead } from '@/types'

withDefaults(
  defineProps<{
    /** The tasks of the current page. */
    tasks: TaskRead[]
    /** The latest workflow run of every task, keyed by task id. */
    workflows?: Record<string, WorkflowRead>
    /** Hide the project column - a page that shows one project does not need it. */
    hideProject?: boolean
    /**
     * Hide the workflow column.
     *
     * A page that lists tasks across every project has no single request
     * that answers the latest run of each task; it hides the column rather
     * than showing "未启动" for tasks that do have runs.
     */
    hideWorkflow?: boolean
  }>(),
  { workflows: () => ({}), hideProject: false, hideWorkflow: false },
)

const emit = defineEmits<{
  /** The user opened the details of a task. */
  (event: 'view', task: TaskRead): void
  /** The user asked to edit a task. */
  (event: 'edit', task: TaskRead): void
  /** The user opened the workflow run of a task. */
  (event: 'view-workflow', workflow: WorkflowRead): void
}>()

function splitDateTime(value: string): { date: string; time: string } {
  const [date, time = ''] = formatDateTime(value).split(' ')
  return { date, time }
}
</script>

<template>
  <el-table class="task-table" :data="tasks" row-key="id" stripe style="width: 100%">
    <el-table-column label="#" width="56" align="center">
      <template #default="{ row }: { row: TaskRead }">
        <span class="task-table__seq">{{ row.seq }}</span>
      </template>
    </el-table-column>

    <el-table-column label="任务名称" min-width="200">
      <template #default="{ row }: { row: TaskRead }">
        <el-link type="primary" class="task-table__title" @click="emit('view', row)">
          {{ row.title }}
        </el-link>
        <div v-if="!hideProject && row.project_name" class="task-table__sub">
          {{ row.project_code }} · {{ row.project_name }}
        </div>
      </template>
    </el-table-column>

    <el-table-column label="描述" min-width="160" show-overflow-tooltip>
      <template #default="{ row }: { row: TaskRead }">
        <span class="task-table__description">{{ row.description || '—' }}</span>
      </template>
    </el-table-column>

    <el-table-column label="状态" width="88" align="center">
      <template #default="{ row }: { row: TaskRead }">
        <StatusTag :status="row.status" kind="task" />
      </template>
    </el-table-column>

    <el-table-column label="优先级" width="76" align="center">
      <template #default="{ row }: { row: TaskRead }">
        <StatusTag :status="row.priority" kind="priority" />
      </template>
    </el-table-column>

    <el-table-column label="负责人" width="96" show-overflow-tooltip>
      <template #default="{ row }: { row: TaskRead }">
        {{ row.assignee || '—' }}
      </template>
    </el-table-column>

    <el-table-column v-if="!hideWorkflow" label="工作流" width="112" align="center">
      <template #default="{ row }: { row: TaskRead }">
        <el-link
          v-if="workflows[row.id]"
          type="primary"
          underline="never"
          @click="emit('view-workflow', workflows[row.id])"
        >
          <StatusTag :status="workflows[row.id].status" kind="workflow" />
        </el-link>
        <span v-else class="task-table__muted">未启动</span>
      </template>
    </el-table-column>

    <el-table-column label="创建时间" width="110">
      <template #default="{ row }: { row: TaskRead }">
        <div class="task-table__time">
          <span>{{ splitDateTime(row.created_at).date }}</span>
          <span class="task-table__time-part">{{ splitDateTime(row.created_at).time }}</span>
        </div>
      </template>
    </el-table-column>

    <el-table-column label="更新时间" width="110">
      <template #default="{ row }: { row: TaskRead }">
        <div class="task-table__time">
          <span>{{ splitDateTime(row.updated_at).date }}</span>
          <span class="task-table__time-part">{{ splitDateTime(row.updated_at).time }}</span>
        </div>
      </template>
    </el-table-column>

    <el-table-column label="操作" width="120" fixed="right" align="center">
      <template #default="{ row }: { row: TaskRead }">
        <el-button link type="primary" size="small" @click="emit('view', row)">详情</el-button>
        <el-button link type="primary" size="small" @click="emit('edit', row)">编辑</el-button>
      </template>
    </el-table-column>
  </el-table>
</template>

<style scoped>
.task-table__seq {
  color: var(--el-text-color-secondary);
  font-variant-numeric: tabular-nums;
}

.task-table__title {
  font-weight: 500;
}

.task-table__sub,
.task-table__muted {
  color: var(--el-text-color-secondary);
  font-size: 12px;
}

.task-table__description {
  color: var(--el-text-color-regular);
}

.task-table__time {
  display: flex;
  flex-direction: column;
  line-height: 1.4;
}

.task-table__time-part {
  color: var(--el-text-color-secondary);
  font-size: 12px;
}
</style>
