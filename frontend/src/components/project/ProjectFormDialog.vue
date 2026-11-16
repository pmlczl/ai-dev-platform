<script setup lang="ts">
/**
 * The dialog that creates and edits a project.
 *
 * Both operations use the same form: the fields are the ones of the backend
 * schema `ProjectCreate` / `ProjectUpdate`, nothing is added to them.
 */
import { computed, nextTick, reactive, ref, watch } from 'vue'
import type { FormInstance, FormRules } from 'element-plus'

import { PROJECT_STATUS_OPTIONS } from '@/constants/status'

import type { ProjectRead, ProjectStatus } from '@/types'

/** The values the dialog hands back to the page. */
interface ProjectFormPayload {
  code: string
  name: string
  description: string | null
  status: ProjectStatus
  owner: string | null
}

/** The pattern the backend accepts for a project code. */
const CODE_PATTERN = /^[A-Za-z0-9][A-Za-z0-9._-]*$/

const props = withDefaults(
  defineProps<{
    /** The dialog is open. */
    modelValue: boolean
    /** The project that is edited - without it a new project is created. */
    project?: ProjectRead | null
    /** The request is running - the dialog must not be submitted twice. */
    submitting?: boolean
  }>(),
  { project: null, submitting: false },
)

const emit = defineEmits<{
  (event: 'update:modelValue', value: boolean): void
  (event: 'submit', payload: ProjectFormPayload): void
}>()

const formRef = ref<FormInstance>()
const form = reactive({
  code: '',
  name: '',
  description: '',
  status: 'planning' as ProjectStatus,
  owner: '',
})

/** True when an existing project is edited. */
const isEdit = computed(() => props.project !== null)

const title = computed(() => (isEdit.value ? '编辑项目' : '新建项目'))

const rules: FormRules = {
  code: [
    { required: true, message: '请输入项目编号', trigger: 'blur' },
    {
      pattern: CODE_PATTERN,
      message: '只能包含字母、数字、点、下划线和连字符，且以字母或数字开头',
      trigger: 'blur',
    },
    { max: 64, message: '项目编号最多 64 个字符', trigger: 'blur' },
  ],
  name: [
    { required: true, message: '请输入项目名称', trigger: 'blur' },
    { max: 200, message: '项目名称最多 200 个字符', trigger: 'blur' },
  ],
  description: [{ max: 5000, message: '项目描述最多 5000 个字符', trigger: 'blur' }],
  owner: [{ max: 120, message: '负责人最多 120 个字符', trigger: 'blur' }],
}

/** The visibility of the dialog, bound to the model of the page. */
const visible = computed({
  get: () => props.modelValue,
  set: (value: boolean) => emit('update:modelValue', value),
})

/** Fill the form with the values of the project that is edited. */
watch(
  () => props.project,
  (project) => {
    form.code = project?.code ?? ''
    form.name = project?.name ?? ''
    form.description = project?.description ?? ''
    form.status = project?.status ?? 'planning'
    form.owner = project?.owner ?? ''
    void nextTick(() => formRef.value?.clearValidate())
  },
  { immediate: true },
)

/** Validate the form and hand the values over to the page. */
async function handleSubmit(): Promise<void> {
  if (props.submitting) {
    return
  }
  const valid = await formRef.value?.validate().catch(() => false)
  if (!valid) {
    return
  }
  emit('submit', {
    code: form.code.trim(),
    name: form.name.trim(),
    description: form.description.trim() ? form.description.trim() : null,
    status: form.status,
    owner: form.owner.trim() ? form.owner.trim() : null,
  })
}
</script>

<template>
  <el-dialog
    v-model="visible"
    :title="title"
    width="560px"
    :close-on-click-modal="false"
    :close-on-press-escape="!submitting"
    :show-close="!submitting"
  >
    <el-form
      ref="formRef"
      class="project-form"
      :model="form"
      :rules="rules"
      label-width="90px"
      label-position="right"
    >
      <el-form-item label="项目编号" prop="code">
        <el-input
          v-model="form.code"
          placeholder="例如 PRJ-2026-001"
          maxlength="64"
          show-word-limit
        />
      </el-form-item>

      <el-form-item label="项目名称" prop="name">
        <el-input
          v-model="form.name"
          placeholder="请输入项目名称"
          maxlength="200"
          show-word-limit
        />
      </el-form-item>

      <el-form-item label="项目描述" prop="description">
        <el-input
          v-model="form.description"
          type="textarea"
          :rows="4"
          placeholder="选填，描述项目的目标与范围"
          maxlength="5000"
          show-word-limit
        />
      </el-form-item>

      <el-form-item label="状态" prop="status">
        <el-select v-model="form.status" placeholder="请选择状态" style="width: 100%">
          <el-option
            v-for="option in PROJECT_STATUS_OPTIONS"
            :key="option.value"
            :label="option.label"
            :value="option.value"
          />
        </el-select>
      </el-form-item>

      <el-form-item label="负责人" prop="owner">
        <el-input v-model="form.owner" placeholder="选填" maxlength="120" show-word-limit />
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
.project-form {
  padding-right: 12px;
}
</style>
