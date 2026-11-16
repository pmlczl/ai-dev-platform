<script setup lang="ts">
/**
 * The event log of a workflow run.
 *
 * The rows are shown in the order the backend sends them - oldest first -
 * and the payload of an event is opened on demand. An event that marks a
 * problem is highlighted.
 */
import { WORKFLOW_ERROR_EVENTS, workflowEventLabel, workflowNodeLabel } from '@/constants/workflow'
import { formatDateTime } from '@/utils/format'

import type { WorkflowEventRead } from '@/types'

defineProps<{
  events: WorkflowEventRead[]
}>()

function rowClassName({ row }: { row: WorkflowEventRead }): string {
  return WORKFLOW_ERROR_EVENTS.has(row.event) ? 'workflow-events__row--error' : ''
}

function formatPayload(payload: Record<string, unknown> | null): string {
  if (!payload) {
    return ''
  }
  return JSON.stringify(payload, null, 2)
}

function hasPayload(payload: Record<string, unknown> | null): boolean {
  return Boolean(payload && Object.keys(payload).length > 0)
}
</script>

<template>
  <el-table
    class="workflow-events"
    :data="events"
    row-key="sequence"
    stripe
    style="width: 100%"
    :row-class-name="rowClassName"
  >
    <el-table-column type="expand" width="40">
      <template #default="{ row }: { row: WorkflowEventRead }">
        <div class="workflow-events__expand">
          <p class="workflow-events__message">{{ row.message || '（无内容）' }}</p>
          <pre v-if="hasPayload(row.payload)" class="workflow-events__payload">{{ formatPayload(row.payload) }}</pre>
          <p v-else class="workflow-events__muted">该事件没有附加数据</p>
        </div>
      </template>
    </el-table-column>

    <el-table-column label="序号" prop="sequence" width="64" align="center" />

    <el-table-column label="时间" width="160">
      <template #default="{ row }: { row: WorkflowEventRead }">
        {{ formatDateTime(row.created_at) }}
      </template>
    </el-table-column>

    <el-table-column label="节点" width="130" show-overflow-tooltip>
      <template #default="{ row }: { row: WorkflowEventRead }">
        {{ workflowNodeLabel(row.step) }}
      </template>
    </el-table-column>

    <el-table-column label="事件" width="130" show-overflow-tooltip>
      <template #default="{ row }: { row: WorkflowEventRead }">
        <span :class="{ 'workflow-events__error': WORKFLOW_ERROR_EVENTS.has(row.event) }">
          {{ workflowEventLabel(row.event) }}
        </span>
      </template>
    </el-table-column>

    <el-table-column label="内容" min-width="260" show-overflow-tooltip>
      <template #default="{ row }: { row: WorkflowEventRead }">
        {{ row.message || '—' }}
      </template>
    </el-table-column>
  </el-table>
</template>

<style scoped>
.workflow-events :deep(.workflow-events__row--error) {
  --el-table-tr-bg-color: var(--el-color-danger-light-9);
}

.workflow-events__error {
  color: var(--el-color-danger);
  font-weight: 600;
}

.workflow-events__expand {
  padding: 4px 12px 8px 52px;
}

.workflow-events__message {
  margin: 0 0 8px;
  white-space: pre-wrap;
  word-break: break-word;
}

.workflow-events__payload {
  margin: 0;
  padding: 10px 12px;
  max-height: 320px;
  overflow: auto;
  font-size: 12px;
  line-height: 1.5;
  background: var(--el-fill-color-light);
  border-radius: 4px;
  white-space: pre-wrap;
  word-break: break-all;
}

.workflow-events__muted {
  margin: 0;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
</style>
