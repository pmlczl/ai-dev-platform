<script setup lang="ts">
/**
 * The dialog that starts a workflow run for a task.
 *
 * The run is executed by the backend; the dialog only asks which registered
 * workflow to run and who starts it. The id of the run and its thread come
 * back in the answer of the backend - the browser never makes them up.
 */
import { computed, ref, watch } from 'vue'

import { WORKFLOW_KEY_LABELS } from '@/constants/workflow'

import type { WorkflowStartRequest } from '@/types'

const props = withDefaults(
  defineProps<{
    modelValue: boolean
    /** The request is running - the dialog must not be submitted twice. */
    submitting?: boolean
    /** The title of the task - shown so the user knows what is started. */
    taskTitle?: string | null
  }>(),
  { submitting: false, taskTitle: null },
)

const emit = defineEmits<{
  (event: 'update:modelValue', value: boolean): void
  (event: 'submit', payload: WorkflowStartRequest): void
}>()

const WORKFLOW_OPTIONS = Object.entries(WORKFLOW_KEY_LABELS).map(([value, label]) => ({
  value,
  label,
}))

const workflowKey = ref(WORKFLOW_OPTIONS[0]?.value ?? 'dev_workflow')
const startedBy = ref('')

const visible = computed({
  get: () => props.modelValue,
  set: (value: boolean) => emit('update:modelValue', value),
})

watch(
  () => props.modelValue,
  (open) => {
    if (open) {
      workflowKey.value = WORKFLOW_OPTIONS[0]?.value ?? 'dev_workflow'
      startedBy.value = ''
    }
  },
)

function handleSubmit(): void {
  if (props.submitting) {
    return
  }
  const payload: WorkflowStartRequest = { workflow_key: workflowKey.value }
  const name = startedBy.value.trim()
  if (name) {
    payload.started_by = name
  }
  emit('submit', payload)
}
</script>

<template>
  <el-dialog
    v-model="visible"
    title="启动工作流"
    width="520px"
    :close-on-click-modal="false"
    :close-on-press-escape="!submitting"
    destroy-on-close
  >
    <el-alert
      type="info"
      :closable="false"
      show-icon
      class="workflow-start__alert"
      title="当前为本地模拟工作流：产物由固定模板生成，不会调用任何 AI 模型。"
    />
    <el-form label-width="90px" label-position="right" @submit.prevent="handleSubmit">
      <el-form-item v-if="taskTitle" label="任务">
        <span class="workflow-start__task">{{ taskTitle }}</span>
      </el-form-item>
      <el-form-item label="工作流类型">
        <el-select v-model="workflowKey" style="width: 100%">
          <el-option
            v-for="option in WORKFLOW_OPTIONS"
            :key="option.value"
            :label="option.label"
            :value="option.value"
          />
        </el-select>
      </el-form-item>
      <el-form-item label="发起人">
        <el-input
          v-model="startedBy"
          placeholder="可选，记录在工作流事件中"
          maxlength="120"
          show-word-limit
        />
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button :disabled="submitting" @click="visible = false">取消</el-button>
      <el-button type="primary" :loading="submitting" @click="handleSubmit">确认启动</el-button>
    </template>
  </el-dialog>
</template>

<style scoped>
.workflow-start__alert {
  margin-bottom: 16px;
}

.workflow-start__task {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
</style>
