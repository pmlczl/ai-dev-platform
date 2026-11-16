<script setup lang="ts">
/**
 * The dialog that records a human approval decision.
 *
 * The platform has no login and no roles, so the name of the approver is
 * self-reported: it is stored as it is typed and the dialog says so. The
 * decision itself always goes to the backend, which validates the state of
 * the run and writes the record.
 *
 * A rejection needs a reason - the run goes back to the generation node and
 * the reason is the only instruction the next round gets. A confirmation
 * step before the submission keeps an accidental click from deciding a run.
 */
import { computed, reactive, ref, watch } from 'vue'
import { ElMessageBox } from 'element-plus'

import { APPROVER_MAX_LENGTH, DECISION_COMMENT_MAX_LENGTH } from '@/constants/approval'

const props = withDefaults(
  defineProps<{
    modelValue: boolean
    /** The decision the user picked. */
    decision: 'approved' | 'rejected'
    /** The run that is decided - only used in the wording. */
    workflowShortId?: string | null
    /** The file the decision is about. */
    artifactName?: string | null
    /** The request is running - the dialog must not be submitted twice. */
    submitting?: boolean
  }>(),
  { workflowShortId: null, artifactName: null, submitting: false },
)

const emit = defineEmits<{
  (event: 'update:modelValue', value: boolean): void
  (event: 'submit', payload: { approver: string; comment: string | null }): void
}>()

const form = reactive({ approver: '', comment: '' })
const approverError = ref<string | null>(null)
const commentError = ref<string | null>(null)

const visible = computed({
  get: () => props.modelValue,
  set: (value: boolean) => emit('update:modelValue', value),
})

const title = computed(() => (props.decision === 'approved' ? '通过审批' : '驳回审批'))

watch(
  () => props.modelValue,
  (open) => {
    if (open) {
      form.approver = ''
      form.comment = ''
      approverError.value = null
      commentError.value = null
    }
  },
)

function validate(): boolean {
  const approver = form.approver.trim()
  const comment = form.comment.trim()
  approverError.value = approver ? null : '请填写审批人'
  commentError.value =
    props.decision === 'rejected' && !comment ? '驳回必须填写理由，下一轮生成依赖这段说明。' : null
  return !approverError.value && !commentError.value
}

async function handleSubmit(): Promise<void> {
  if (props.submitting || !validate()) {
    return
  }
  const approver = form.approver.trim()
  const comment = form.comment.trim() || null
  const target = props.artifactName ? `产物「${props.artifactName}」` : '本轮产物'
  const run = props.workflowShortId ? `工作流 ${props.workflowShortId} 的` : ''
  const summary =
    props.decision === 'approved'
      ? `确认通过${run}${target}？通过后本轮被接受，运行进入完成。`
      : `确认驳回${run}${target}？驳回后运行回到生成节点，按这条理由产出下一轮产物：${comment}`
  try {
    await ElMessageBox.confirm(summary, title.value, {
      type: props.decision === 'approved' ? 'warning' : 'error',
      confirmButtonText: '确认提交',
      cancelButtonText: '返回修改',
    })
  } catch {
    // The user went back to the form; nothing was sent.
    return
  }
  emit('submit', { approver, comment })
}
</script>

<template>
  <el-dialog
    v-model="visible"
    :title="title"
    width="560px"
    :close-on-click-modal="false"
    :close-on-press-escape="!submitting"
  >
    <el-alert
      type="info"
      :closable="false"
      show-icon
      title="平台当前没有登录与权限校验，审批人为自报姓名，仅作为记录写入审批历史。"
      class="approval-decision__alert"
    />
    <p v-if="artifactName" class="approval-decision__file">
      审批对象：<strong>{{ artifactName }}</strong>
      <span v-if="workflowShortId">（工作流 {{ workflowShortId }}）</span>
    </p>

    <el-form label-width="88px" label-position="right" @submit.prevent="handleSubmit">
      <el-form-item label="审批人" required :error="approverError ?? undefined">
        <el-input
          v-model="form.approver"
          :maxlength="APPROVER_MAX_LENGTH"
          show-word-limit
          placeholder="姓名或工号，写入审批记录"
          :disabled="submitting"
        />
      </el-form-item>
      <el-form-item
        :label="decision === 'rejected' ? '驳回理由' : '审批意见'"
        :required="decision === 'rejected'"
        :error="commentError ?? undefined"
      >
        <el-input
          v-model="form.comment"
          type="textarea"
          :rows="4"
          :maxlength="DECISION_COMMENT_MAX_LENGTH"
          show-word-limit
          :placeholder="
            decision === 'rejected'
              ? '必填：说明需要修改的地方，下一轮生成会读取这段意见'
              : '可选：补充说明通过的原因或注意事项'
          "
          :disabled="submitting"
        />
      </el-form-item>
    </el-form>

    <template #footer>
      <el-button :disabled="submitting" @click="visible = false">取消</el-button>
      <el-button
        :type="decision === 'approved' ? 'primary' : 'danger'"
        :loading="submitting"
        @click="handleSubmit"
      >
        {{ decision === 'approved' ? '确认通过' : '确认驳回' }}
      </el-button>
    </template>
  </el-dialog>
</template>

<style scoped>
.approval-decision__alert {
  margin-bottom: 12px;
}

.approval-decision__file {
  margin: 0 0 14px;
  color: var(--el-text-color-regular);
  font-size: 13px;
}
</style>
