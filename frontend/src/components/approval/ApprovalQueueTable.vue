<script setup lang="ts">
/**
 * The table of the runs that wait for a human decision.
 *
 * A row shows what an approver needs before opening the decision: which run
 * it is, whose task it belongs to, which file is waiting and for how long.
 * Every value comes from the workflow the backend sent - the name of the
 * file is the path of the artifact record, the size and the version are its
 * own fields, and the waiting time is counted from the timestamp of the
 * approval request. The cell is recalculated whenever the page loads the
 * queue again, which is what the polling of the list page does.
 */
import StatusTag from '@/components/common/StatusTag.vue'
import { formatDateTime, formatElapsedSince, formatFileSize } from '@/utils/format'

import type { ProjectRead, TaskRead, WorkflowRead } from '@/types'

withDefaults(
  defineProps<{
    workflows: WorkflowRead[]
    /** The projects behind `project_id`, keyed by id. */
    projects?: Record<string, ProjectRead>
    /** The tasks behind `task_id`, keyed by id. */
    tasks?: Record<string, TaskRead>
  }>(),
  { projects: () => ({}), tasks: () => ({}) },
)

const emit = defineEmits<{
  /** The user opened the decision page of a run. */
  (event: 'decide', workflow: WorkflowRead): void
  (event: 'view-workflow', workflow: WorkflowRead): void
  (event: 'view-task', taskId: string): void
}>()

function shortId(id: string): string {
  return id.split('-')[0]
}

/**
 * The file the decision is about.
 *
 * `pending_approval.artifact_id` names it; `current_artifact` carries its
 * metadata and is the record of the same round. Without either the run has
 * no file to show.
 */
function artifactOf(workflow: WorkflowRead) {
  return workflow.current_artifact
}

/** The version of that file - the pending request states it, the artifact agrees. */
function artifactVersion(workflow: WorkflowRead): number | null {
  return workflow.pending_approval?.artifact_version ?? workflow.current_artifact?.version ?? null
}
</script>

<template>
  <el-table class="approval-queue-table" :data="workflows" row-key="id" stripe style="width: 100%">
    <el-table-column label="工作流 ID" width="112">
      <template #default="{ row }: { row: WorkflowRead }">
        <el-tooltip :content="row.id" placement="top">
          <el-link type="primary" underline="never" @click="emit('view-workflow', row)">
            {{ shortId(row.id) }}
          </el-link>
        </el-tooltip>
      </template>
    </el-table-column>

    <el-table-column label="项目" min-width="150" show-overflow-tooltip>
      <template #default="{ row }: { row: WorkflowRead }">
        {{ projects[row.project_id]?.name ?? row.project_id.split('-')[0] }}
      </template>
    </el-table-column>

    <el-table-column label="任务" min-width="170">
      <template #default="{ row }: { row: WorkflowRead }">
        <el-link
          v-if="row.task_id"
          type="primary"
          underline="never"
          class="approval-queue-table__ellipsis"
          @click="emit('view-task', row.task_id)"
        >
          {{
            row.task_id && tasks[row.task_id]
              ? `#${tasks[row.task_id]?.seq} ${tasks[row.task_id]?.title}`
              : row.task_id.split('-')[0]
          }}
        </el-link>
        <span v-else class="approval-queue-table__muted">—</span>
      </template>
    </el-table-column>

    <el-table-column label="轮次" width="72" align="center">
      <template #default="{ row }: { row: WorkflowRead }">{{ row.iteration }}</template>
    </el-table-column>

    <el-table-column label="待审批产物" min-width="200">
      <template #default="{ row }: { row: WorkflowRead }">
        <template v-if="artifactOf(row)">
          <el-tooltip :content="artifactOf(row)?.relative_path" placement="top">
            <span class="approval-queue-table__ellipsis">
              {{ artifactOf(row)?.relative_path.split('/').pop() }}
            </span>
          </el-tooltip>
          <div class="approval-queue-table__sub">
            v{{ artifactVersion(row) }} · {{ formatFileSize(artifactOf(row)?.size_bytes) }}
          </div>
        </template>
        <span v-else class="approval-queue-table__muted">本轮没有产物</span>
      </template>
    </el-table-column>

    <el-table-column label="状态" width="88" align="center">
      <template #default="{ row }: { row: WorkflowRead }">
        <StatusTag :status="row.status" kind="workflow" />
      </template>
    </el-table-column>

    <el-table-column label="发起时间" width="150">
      <template #default="{ row }: { row: WorkflowRead }">
        <template v-if="row.pending_approval">
          {{ formatDateTime(row.pending_approval.requested_at) }}
        </template>
        <span v-else class="approval-queue-table__muted">—</span>
      </template>
    </el-table-column>

    <el-table-column label="等待时长" width="116">
      <template #default="{ row }: { row: WorkflowRead }">
        <template v-if="row.pending_approval">
          {{ formatElapsedSince(row.pending_approval.requested_at) }}
        </template>
        <span v-else class="approval-queue-table__muted">—</span>
      </template>
    </el-table-column>

    <el-table-column label="操作" width="88" fixed="right" align="center">
      <template #default="{ row }: { row: WorkflowRead }">
        <el-button link type="primary" size="small" @click="emit('decide', row)">审批</el-button>
      </template>
    </el-table-column>
  </el-table>
</template>

<style scoped>
.approval-queue-table__ellipsis {
  display: inline-block;
  max-width: 100%;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  vertical-align: bottom;
}

.approval-queue-table__sub {
  color: var(--el-text-color-secondary);
  font-size: 12px;
}

.approval-queue-table__muted {
  color: var(--el-text-color-secondary);
}
</style>
