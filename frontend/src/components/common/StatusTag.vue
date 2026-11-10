<script setup lang="ts">
import { computed } from 'vue'

/**
 * The one place that knows how a status is presented.
 *
 * The backend sends the raw values of its enumerations. The mapping to a
 * label and to a colour lives here, so a page never writes it a second time.
 */
type TagType = 'primary' | 'success' | 'info' | 'warning' | 'danger'

interface StatusEntry {
  label: string
  type: TagType
}

/** The status groups the platform knows. */
type StatusKind = 'project' | 'task' | 'workflow' | 'artifact'

const STATUS_MAPS: Record<StatusKind, Record<string, StatusEntry>> = {
  project: {
    planning: { label: '规划中', type: 'info' },
    active: { label: '进行中', type: 'primary' },
    paused: { label: '已暂停', type: 'warning' },
    completed: { label: '已完成', type: 'success' },
    archived: { label: '已归档', type: 'info' },
    cancelled: { label: '已取消', type: 'danger' },
  },
  task: {
    pending: { label: '待处理', type: 'info' },
    in_progress: { label: '开发中', type: 'primary' },
    blocked: { label: '已阻塞', type: 'danger' },
    in_review: { label: '待审核', type: 'warning' },
    completed: { label: '已完成', type: 'success' },
    cancelled: { label: '已取消', type: 'info' },
  },
  workflow: {
    pending: { label: '待启动', type: 'info' },
    running: { label: '执行中', type: 'primary' },
    paused: { label: '已暂停', type: 'warning' },
    waiting_approval: { label: '待审批', type: 'warning' },
    completed: { label: '已完成', type: 'success' },
    failed: { label: '已失败', type: 'danger' },
    cancelled: { label: '已取消', type: 'info' },
  },
  artifact: {
    pending: { label: '待审核', type: 'info' },
    approved: { label: '已通过', type: 'success' },
    rejected: { label: '已驳回', type: 'danger' },
    superseded: { label: '已被替换', type: 'info' },
  },
}

/** The approval decisions - they are shown next to the artifact states. */
const DECISION_MAP: Record<string, StatusEntry> = {
  approved: { label: '已通过', type: 'success' },
  rejected: { label: '已驳回', type: 'danger' },
  changes_requested: { label: '要求修改', type: 'warning' },
}

/** The priorities of a task. */
const PRIORITY_MAP: Record<string, StatusEntry> = {
  low: { label: '低', type: 'info' },
  medium: { label: '中', type: 'info' },
  high: { label: '高', type: 'warning' },
  urgent: { label: '紧急', type: 'danger' },
}

const props = withDefaults(
  defineProps<{
    /** The raw value the backend sent. */
    status: string
    /**
     * The group the value belongs to.
     *
     * When it is left out, every group is searched - the value of a status
     * is unique across the groups.
     */
    kind?: StatusKind | 'decision' | 'priority'
  }>(),
  { kind: undefined },
)

const entry = computed<StatusEntry>(() => {
  if (props.kind === 'decision') {
    return DECISION_MAP[props.status] ?? { label: props.status, type: 'info' }
  }
  if (props.kind === 'priority') {
    return PRIORITY_MAP[props.status] ?? { label: props.status, type: 'info' }
  }
  if (props.kind) {
    const found = STATUS_MAPS[props.kind][props.status]
    return found ?? { label: props.status, type: 'info' }
  }
  for (const map of Object.values(STATUS_MAPS)) {
    const found = map[props.status]
    if (found) {
      return found
    }
  }
  return { label: props.status, type: 'info' }
})
</script>

<template>
  <el-tag :type="entry.type" size="small" effect="light">{{ entry.label }}</el-tag>
</template>
