<script setup lang="ts">
/**
 * The dialog that creates and edits a task.
 *
 * The fields are the ones of the backend schema `TaskCreate` / `TaskUpdate`:
 * title, description, status, priority and assignee. The project of a new
 * task is decided by the page that opens the dialog, never typed in here.
 */
import { computed, nextTick, reactive, ref, watch } from 'vue'
import type { FormInstance, FormRules } from 'element-plus'

import { PRIORITY_MAP, statusOptions } from '@/constants/status'

import type { TaskPriority, TaskRead, TaskStatus } from '@/types'

/** The values the dialog hands back to the page. */
export interface TaskFormPayload {
  title: string
  description: string | null
  status: TaskStatus
  priority: TaskPriority
  assignee: string | null
}

const props = withDefaults(
  defineProps<{
    /** The dialog is open. */
    modelValue: boolean
    /** The task that is edited - without it a new task is created. */
    task?: TaskRead | null
    /** The request is running - the dialog must not be submitted twice. */
    submitting?: boolean
  }>(),
  { task: null, submitting: false },
)

const emit = defineEmits<{
  (event: 'update:modelValue', value: boolean): void
  (event: 'submit', payload: TaskFormPayload): void
}>()

const TASK_STATUS_OPTIONS = statusOptions('task')
const PRIORITY_OPTIONS = Object.entries(PRIORITY_MAP).map(([value, entry]) => ({
  value,
  label: entry.label,
}))

const formRef = ref<FormInstance>()
const form = reactive({
  title: '',
  description: '',
  status: 'pending' as TaskStatus,
  priority: 'medium' as TaskPriority,
  assignee: '',
})

const isEdit = computed(() => props.task !== null)
const title = computed(() => (isEdit.value ? '编辑任务' : '新建任务'))

const rules: FormRules = {
  title: [
    { required: true, message: '请输入任务名称', trigger: 'blur' },
    { max: 300, message: '任务名称最多 300 个字符', trigger: 'blur' },
  ],
  description: [{ max: 5000, message: '任务描述最多 5000 个字符', trigger: 'blur' }],
  assignee: [{ max: 120, message: '负责人最多 120 个字符', trigger: 'blur' }],
}

const visible = computed({
  get: () => props.modelValue,
  set: (value: boolean) => emit('update:modelValue', value),
})

watch(
  () => [props.task, props.modelValue] as const,
  ([task]) => {
    form.title = task?.title ?? ''
    form.description = task?.description ?? ''
    form.status = task?.status ?? 'pending'
    form.priority = task?.priority ?? 'medium'
    form.assignee = task?.assignee ?? ''
    void nextTick(() => formRef.value?.clearValidate())
  },
  { immediate: true },
)

async function handleSubmit(): Promise<void> {
  if (props.submitting) {
    return
  }
  const valid = await formRef.value?.validate().catch(() => false)
  if (!valid) {
    return
  }
  emit('submit', {
    title: form.title.trim(),
    description: form.description.trim() ? form.description.trim() : null,
    status: form.status,
    priority: form.priority,
    assignee: form.assignee.trim() ? form.assignee.trim() : null,
  })
}
</script>

<template>
  <el-dialog
    v-model="visible"
    :title="title"
    width="560px"
    :close-on-click-modal="false"
    destroy-on-close
  >
    <el-form ref="formRef" :model="form" :rules="rules" label-width="88px" @submit.prevent>
      <el-form-item label="任务名称" prop="title">
        <el-input v-model="form.title" maxlength="300" show-word-limit placeholder="请输入任务名称" />
      </el-form-item>
      <el-form-item label="任务描述" prop="description">
        <el-input
          v-model="form.description"
          type="textarea"
          :rows="4"
          maxlength="5000"
          show-word-limit
          placeholder="可选，描述任务的目标与范围"
        />
      </el-form-item>
      <el-form-item label="状态" prop="status">
        <el-select v-model="form.status" class="task-form__select">
          <el-option
            v-for="option in TASK_STATUS_OPTIONS"
            :key="option.value"
            :label="option.label"
            :value="option.value"
          />
        </el-select>
      </el-form-item>
      <el-form-item label="优先级" prop="priority">
        <el-select v-model="form.priority" class="task-form__select">
          <el-option
            v-for="option in PRIORITY_OPTIONS"
            :key="option.value"
            :label="option.label"
            :value="option.value"
          />
        </el-select>
      </el-form-item>
      <el-form-item label="负责人" prop="assignee">
        <el-input v-model="form.assignee" maxlength="120" placeholder="可选" />
      </el-form-item>
    </el-form>

    <template #footer>
      <el-button :disabled="submitting" @click="visible = false">取消</el-button>
      <el-button type="primary" :loading="submitting" @click="handleSubmit">
        {{ isEdit ? '保存' : '创建' }}
      </el-button>
    </template>
  </el-dialog>
</template>

<style scoped>
.task-form__select {
  width: 100%;
}
</style>
