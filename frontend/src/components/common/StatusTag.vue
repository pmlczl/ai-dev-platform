<script setup lang="ts">
import { computed } from 'vue'

import {
  DECISION_MAP,
  PRIORITY_MAP,
  STATUS_MAPS,
} from '@/constants/status'

import type { StatusEntry, StatusKind } from '@/constants/status'

/**
 * The one place that knows how a status is presented.
 *
 * The backend sends the raw values of its enumerations. The mapping to a
 * label and to a colour lives in `@/constants/status`, so a page never writes
 * it a second time.
 */
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
