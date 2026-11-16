<script setup lang="ts">
/**
 * The table of workflow runs.
 *
 * It is used by the project detail (the runs of a project), the task detail
 * (the runs of a task) and the monitoring page (every run). The names of the
 * project and the task come from the page - the backend sends their ids
 * only, and the page resolves them once for all rows.
 */
import StatusTag from '@/components/common/StatusTag.vue'
import { workflowKeyLabel, workflowNodeLabel } from '@/constants/workflow'
import { formatDateTime } from '@/utils/format'

import type { ProjectRead, TaskRead, WorkflowRead } from '@/types'

withDefaults(
  defineProps<{
    workflows: WorkflowRead[]
    /** The projects behind `project_id`, keyed by id. */
    projects?: Record<string, ProjectRead>
    /** The tasks behind `task_id`, keyed by id. */
    tasks?: Record<string, TaskRead>
    showProject?: boolean
    showTask?: boolean
  }>(),
  { projects: () => ({}), tasks: () => ({}), showProject: true, showTask: true },
)

const emit = defineEmits<{
  (event: 'view', workflow: WorkflowRead): void
  (event: 'view-task', taskId: string): void
  (event: 'view-project', projectId: string): void
}>()

/** The first block of a UUID - enough to tell two runs apart. */
function shortId(id: string): string {
  return id.split('-')[0]
}

function splitDateTime(value: string | null): { date: string; time: string } {
  if (!value) {
    return { date: '—', time: '' }
  }
  const [date, time = ''] = formatDateTime(value).split(' ')
  return { date, time }
}
</script>

<template>
  <el-table class="workflow-table" :data="workflows" row-key="id" stripe style="width: 100%">
    <el-table-column label="工作流 ID" width="120">
      <template #default="{ row }: { row: WorkflowRead }">
        <el-tooltip :content="row.id" placement="top">
          <el-link type="primary" class="workflow-table__id" @click="emit('view', row)">
            {{ shortId(row.id) }}
          </el-link>
        </el-tooltip>
      </template>
    </el-table-column>

    <el-table-column v-if="showProject" label="项目" min-width="150" show-overflow-tooltip>
      <template #default="{ row }: { row: WorkflowRead }">
        <el-link
          v-if="projects[row.project_id]"
          type="primary"
          underline="never"
          @click="emit('view-project', row.project_id)"
        >
          {{ projects[row.project_id].name }}
        </el-link>
        <span v-else class="workflow-table__muted" :title="row.project_id">
          {{ shortId(row.project_id) }}
        </span>
      </template>
    </el-table-column>

    <el-table-column v-if="showTask" label="任务" min-width="180" show-overflow-tooltip>
      <template #default="{ row }: { row: WorkflowRead }">
        <template v-if="row.task_id">
          <el-link
            v-if="tasks[row.task_id]"
            type="primary"
            underline="never"
            @click="emit('view-task', row.task_id)"
          >
            {{ tasks[row.task_id].title }}
          </el-link>
          <span v-else class="workflow-table__muted" :title="row.task_id">
            {{ shortId(row.task_id) }}
          </span>
        </template>
        <span v-else class="workflow-table__muted">—</span>
      </template>
    </el-table-column>

    <el-table-column label="类型" min-width="130" show-overflow-tooltip>
      <template #default="{ row }: { row: WorkflowRead }">
        {{ workflowKeyLabel(row.workflow_key) }}
      </template>
    </el-table-column>

    <el-table-column label="状态" width="92" align="center">
      <template #default="{ row }: { row: WorkflowRead }">
        <StatusTag :status="row.status" kind="workflow" />
      </template>
    </el-table-column>

    <el-table-column label="轮次" width="60" align="center">
      <template #default="{ row }: { row: WorkflowRead }">
        {{ row.iteration }}
      </template>
    </el-table-column>

    <el-table-column label="当前节点" width="110" show-overflow-tooltip>
      <template #default="{ row }: { row: WorkflowRead }">
        {{ workflowNodeLabel(row.current_step) }}
      </template>
    </el-table-column>

    <el-table-column label="创建时间" width="110">
      <template #default="{ row }: { row: WorkflowRead }">
        <div class="workflow-table__time">
          <span>{{ splitDateTime(row.created_at).date }}</span>
          <span class="workflow-table__time-part">{{ splitDateTime(row.created_at).time }}</span>
        </div>
      </template>
    </el-table-column>

    <el-table-column label="开始时间" width="110">
      <template #default="{ row }: { row: WorkflowRead }">
        <div class="workflow-table__time">
          <span>{{ splitDateTime(row.started_at).date }}</span>
          <span class="workflow-table__time-part">{{ splitDateTime(row.started_at).time }}</span>
        </div>
      </template>
    </el-table-column>

    <el-table-column label="结束时间" width="110">
      <template #default="{ row }: { row: WorkflowRead }">
        <div class="workflow-table__time">
          <span>{{ splitDateTime(row.finished_at).date }}</span>
          <span class="workflow-table__time-part">{{ splitDateTime(row.finished_at).time }}</span>
        </div>
      </template>
    </el-table-column>

    <el-table-column label="操作" width="72" fixed="right" align="center">
      <template #default="{ row }: { row: WorkflowRead }">
        <el-button link type="primary" size="small" @click="emit('view', row)">详情</el-button>
      </template>
    </el-table-column>
  </el-table>
</template>

<style scoped>
.workflow-table__id {
  font-family: var(--el-font-family-mono, ui-monospace, SFMono-Regular, Menlo, monospace);
  font-size: 13px;
}

.workflow-table__muted {
  color: var(--el-text-color-secondary);
  font-size: 12px;
}

.workflow-table__time {
  display: flex;
  flex-direction: column;
  line-height: 1.4;
}

.workflow-table__time-part {
  color: var(--el-text-color-secondary);
  font-size: 12px;
}
</style>
