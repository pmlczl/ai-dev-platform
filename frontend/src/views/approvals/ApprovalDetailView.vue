<script setup lang="ts">
/**
 * The decision page of one workflow run.
 *
 * The page shows what the approval is about - the run, its project and task,
 * the file of the current round and the trail of the earlier decisions - and
 * submits the choice through the resume endpoint of the workflow, the only
 * call that advances a run.
 *
 * Three rules hold the page together:
 *
 * * the thread of the run is the one the backend sent, never one the browser
 *   assembled;
 * * the content of the file comes from the download endpoint only;
 * * a decision is submitted once. The page confirms before it sends, keeps
 *   the button disabled while the request runs, and reuses one client key
 *   per approval request so that a retry cannot store a second record.
 *
 * The platform has no login and no roles: the approver is a self-reported
 * name, recorded as typed and never presented as a verified identity.
 */
import { computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'

import ApprovalDecisionDialog from '@/components/approval/ApprovalDecisionDialog.vue'
import ArtifactPreview from '@/components/approval/ArtifactPreview.vue'
import PageHeader from '@/components/common/PageHeader.vue'
import PageState from '@/components/common/PageState.vue'
import StatusTag from '@/components/common/StatusTag.vue'
import { fetchArtifact } from '@/api/artifacts'
import { describeApiError, isConflictError, isNotFoundError } from '@/api/client'
import { submitWorkflowApproval } from '@/api/approvals'
import { fetchWorkflow } from '@/api/workflows'
import { approvalIdempotencyKey } from '@/constants/approval'
import { statusLabel } from '@/constants/status'
import { workflowKeyLabel, workflowNodeLabel } from '@/constants/workflow'
import { useReferenceStore, useWorkspaceStore } from '@/stores'
import { formatDateTime, formatFileSize, formatPath } from '@/utils/format'

import type { ArtifactRead, WorkflowRead } from '@/types'

const route = useRoute()
const router = useRouter()
const workspace = useWorkspaceStore()
const reference = useReferenceStore()

const workflowId = computed(() => String(route.params.workflow_id ?? ''))

// --- the run ---------------------------------------------------------------------------

const workflow = ref<WorkflowRead | null>(null)
const loading = ref(false)
const error = ref<string | null>(null)
/** The run named by the URL does not exist. */
const missing = ref(false)

let inflight: Promise<void> | null = null

async function load(): Promise<void> {
  if (inflight) {
    return inflight
  }
  loading.value = true
  error.value = null
  inflight = (async () => {
    try {
      const run = await fetchWorkflow(workflowId.value, { silent: true })
      workflow.value = run
      missing.value = false
      error.value = null
      workspace.focusWorkflow(run.id)
      await Promise.all([
        reference.resolveProjects([run.project_id]),
        reference.resolveTasks([run.task_id]),
      ])
      // The file of the round is known from the run, so it is read here. Read
      // it from a watcher on the artifact id as well and the same endpoint is
      // called twice while the page opens.
      await loadArtifact()
    } catch (caught) {
      workflow.value = null
      artifact.value = null
      artifactError.value = null
      missing.value = isNotFoundError(caught)
      error.value = describeApiError(caught)
    } finally {
      loading.value = false
      inflight = null
    }
  })()
  return inflight
}

/**
 * The approval request the run carries.
 *
 * The backend answers it only while a run waits; a decided run has none, and
 * the page then shows the last round read-only.
 */
const pending = computed(() => workflow.value?.pending_approval ?? null)

// --- the file of the current round ---------------------------------------------------------

const artifact = ref<ArtifactRead | null>(null)
const artifactLoading = ref(false)
const artifactError = ref<string | null>(null)

/** The file the pending request names; a decided run falls back to the current one. */
const artifactId = computed<string | null>(
  () => pending.value?.artifact_id ?? workflow.value?.current_artifact?.id ?? null,
)

async function loadArtifact(): Promise<void> {
  const id = artifactId.value
  if (!id) {
    artifact.value = null
    artifactError.value = null
    return
  }
  artifactLoading.value = true
  artifactError.value = null
  try {
    artifact.value = await fetchArtifact(id)
  } catch (caught) {
    artifact.value = null
    artifactError.value = describeApiError(caught)
  } finally {
    artifactLoading.value = false
  }
}

watch(
  workflowId,
  () => {
    void load()
  },
  { immediate: true },
)

// --- the decision -----------------------------------------------------------------------------

const dialogVisible = ref(false)
const decision = ref<'approved' | 'rejected'>('approved')
const submitting = ref(false)

/** The run waits for a decision here and now. */
const isPending = computed(() => workflow.value?.status === 'waiting_approval')

/** The state of the run in the words of the shared mapping. */
const statusText = computed(
  () => (workflow.value ? statusLabel('workflow', workflow.value.status) : ''),
)

const history = computed(() =>
  [...(workflow.value?.approvals ?? [])].sort((left, right) => left.sequence - right.sequence),
)

/** The file of the round, shown by name. */
const artifactName = computed<string | null>(() => {
  const file = artifact.value
  if (!file) {
    return null
  }
  return file.original_filename ?? file.relative_path.split('/').pop() ?? null
})

/** The version the pending request states; the artifact record is the fallback. */
const artifactVersion = computed<number | null>(
  () => pending.value?.artifact_version ?? artifact.value?.version ?? null,
)

/** The task of the run, in the words of the cached task record. */
const taskLabel = computed<string>(() => {
  const taskId = workflow.value?.task_id ?? ''
  const known = reference.tasks[taskId]
  if (known) {
    return `#${known.seq} ${known.title}`
  }
  return taskId.split('-')[0] ?? ''
})

function openDecision(next: 'approved' | 'rejected'): void {
  if (!isPending.value || submitting.value) {
    return
  }
  decision.value = next
  dialogVisible.value = true
}

/** The form of the dialog, as it is submitted to the resume endpoint. */
interface DecisionPayload {
  approver: string
  comment: string | null
}

async function handleDecision(payload: DecisionPayload): Promise<void> {
  const run = workflow.value
  if (!run || submitting.value) {
    return
  }
  submitting.value = true
  try {
    const updated = await submitWorkflowApproval(run.id, {
      // The thread of the run, exactly as the backend sent it.
      thread_id: run.thread_id,
      decision: decision.value,
      approver: payload.approver,
      comment: payload.comment,
      // One key per approval request: a retry of this decision is a no-op.
      idempotency_key: pending.value
        ? approvalIdempotencyKey(pending.value.request_id, decision.value)
        : undefined,
    })
    dialogVisible.value = false
    ElMessage.success(
      decision.value === 'approved'
        ? `已通过，运行状态：${statusLabel('workflow', updated.status)}`
        : `已驳回，运行状态：${statusLabel('workflow', updated.status)}`,
    )
    workflow.value = updated
    await Promise.all([
      reference.resolveProjects([updated.project_id]),
      reference.resolveTasks([updated.task_id]),
      loadArtifact(),
    ])
  } catch (caught) {
    if (isConflictError(caught)) {
      // Somebody decided first, or the run left the approval state: the page
      // shows the real state instead of the one it had loaded.
      await load()
    }
    // Every failure already carries a message of the backend in a toast.
  } finally {
    submitting.value = false
  }
}

// --- navigation ----------------------------------------------------------------------------

function gotoWorkflow(): void {
  if (!workflow.value) {
    return
  }
  void router.push({ name: 'workflow-detail', params: { workflow_id: workflow.value.id } })
}

function gotoTask(): void {
  const taskId = workflow.value?.task_id
  if (!taskId) {
    return
  }
  workspace.focusTask(taskId)
  void router.push({ name: 'task-detail', params: { task_id: taskId } })
}

function gotoProject(): void {
  const projectId = workflow.value?.project_id
  if (!projectId) {
    return
  }
  workspace.focusProject(projectId)
  void router.push({ name: 'project-detail', params: { project_id: projectId } })
}

function shortId(id: string): string {
  return id.split('-')[0]
}
</script>

<template>
  <div class="approval-detail">
    <PageState
      v-if="(loading && !workflow) || error"
      :loading="loading"
      :error="error"
      loading-text="正在加载待审批的运行…"
      min-height="320px"
    >
      <template #error>
        <p v-if="missing" class="approval-detail__hint">该审批不存在，或对应的运行已被删除。</p>
        <div class="approval-detail__actions">
          <el-button @click="router.push({ name: 'approvals' })">返回审批列表</el-button>
          <el-button type="primary" @click="load">重试</el-button>
        </div>
      </template>
    </PageState>

    <template v-else-if="workflow">
      <PageHeader
        :title="`审批 · 工作流 ${shortId(workflow.id)}`"
        back-to="{ name: 'approvals' }"
        back-text="审批列表"
      >
        <template #subtitle>
          {{ workflowKeyLabel(workflow.workflow_key) }} · 第 {{ workflow.iteration }} 轮
        </template>
        <template #tags>
          <StatusTag :status="workflow.status" kind="workflow" />
          <el-tag v-if="!isPending" size="small" type="info" effect="plain">本页只读</el-tag>
        </template>
        <template #actions>
          <el-button :loading="loading" @click="load">
            <el-icon><Refresh /></el-icon>
            <span>刷新</span>
          </el-button>
          <el-button @click="gotoWorkflow">
            <el-icon><Connection /></el-icon>
            <span>工作流详情</span>
          </el-button>
          <el-button
            v-if="isPending"
            type="danger"
            plain
            :loading="submitting"
            @click="openDecision('rejected')"
          >
            <el-icon><Close /></el-icon>
            <span>驳回</span>
          </el-button>
          <el-button
            v-if="isPending"
            type="primary"
            :loading="submitting"
            @click="openDecision('approved')"
          >
            <el-icon><Check /></el-icon>
            <span>通过</span>
          </el-button>
        </template>
      </PageHeader>

      <el-alert
        v-if="!isPending"
        type="info"
        :closable="false"
        show-icon
        class="approval-detail__alert"
        :title="`该运行当前为「${statusText}」，不在待审批状态，不能提交审批决定。`"
      />
      <el-alert
        v-else-if="history.length > 0"
        type="warning"
        :closable="false"
        show-icon
        class="approval-detail__alert"
        :title="`本轮之前已有 ${history.length} 次决定；当前是第 ${workflow.iteration} 轮的审批请求，提交后立即生效。`"
      />

      <el-card shadow="never" class="approval-detail__card">
        <template #header><span class="approval-detail__card-title">审批对象</span></template>
        <el-descriptions :column="3" border>
          <el-descriptions-item label="所属项目">
            <el-link type="primary" underline="never" @click="gotoProject">
              {{ reference.projects[workflow.project_id]?.name ?? shortId(workflow.project_id) }}
            </el-link>
            <span v-if="reference.projects[workflow.project_id]" class="approval-detail__code">
              ({{ reference.projects[workflow.project_id]?.code }})
            </span>
          </el-descriptions-item>
          <el-descriptions-item label="所属任务">
            <el-link v-if="workflow.task_id" type="primary" underline="never" @click="gotoTask">
              {{ taskLabel }}
            </el-link>
            <span v-else>—</span>
          </el-descriptions-item>
          <el-descriptions-item label="工作流类型">
            {{ workflowKeyLabel(workflow.workflow_key) }}
          </el-descriptions-item>
          <el-descriptions-item label="运行状态">
            <StatusTag :status="workflow.status" kind="workflow" />
          </el-descriptions-item>
          <el-descriptions-item label="当前节点">
            {{ workflowNodeLabel(workflow.current_step) }}
            <span v-if="workflow.current_step" class="approval-detail__raw">
              ({{ workflow.current_step }})
            </span>
          </el-descriptions-item>
          <el-descriptions-item label="轮次">第 {{ workflow.iteration }} 轮</el-descriptions-item>
          <el-descriptions-item label="审批请求 ID">
            {{ pending?.request_id ?? '—' }}
          </el-descriptions-item>
          <el-descriptions-item label="发起时间">
            {{ pending?.requested_at ? formatDateTime(pending.requested_at) : '—' }}
          </el-descriptions-item>
          <el-descriptions-item label="开始时间">
            {{ formatDateTime(workflow.started_at) }}
          </el-descriptions-item>
          <el-descriptions-item label="工作流 ID" :span="3">{{ workflow.id }}</el-descriptions-item>
        </el-descriptions>
      </el-card>

      <el-card shadow="never" class="approval-detail__card">
        <template #header>
          <div class="approval-detail__card-header">
            <span class="approval-detail__card-title">待审批产物</span>
            <el-tag size="small" type="warning" effect="plain">模拟成果</el-tag>
            <el-button class="approval-detail__card-action" size="small" text @click="loadArtifact">
              <el-icon><Refresh /></el-icon>
              <span>刷新</span>
            </el-button>
          </div>
        </template>

        <PageState
          :loading="artifactLoading"
          :error="artifactError"
          :empty="!artifactLoading && !artifactError && !artifact"
          empty-text="本轮没有待审批的产物文件"
          loading-text="正在读取产物…"
          min-height="160px"
        >
          <template #error>
            <el-button type="primary" plain @click="loadArtifact">重试</el-button>
          </template>

          <template v-if="artifact">
            <el-descriptions :column="4" border class="approval-detail__artifact">
              <el-descriptions-item label="文件名" :span="2">
                <el-tooltip :content="artifact.relative_path" placement="top">
                  <span class="approval-detail__ellipsis">
                    {{ formatPath(artifact.relative_path, 60) }}
                  </span>
                </el-tooltip>
              </el-descriptions-item>
              <el-descriptions-item label="版本">v{{ artifactVersion }}</el-descriptions-item>
              <el-descriptions-item label="大小">
                {{ formatFileSize(artifact.size_bytes) }}
              </el-descriptions-item>
              <el-descriptions-item label="审核状态">
                <StatusTag :status="artifact.review_status" kind="artifact" />
              </el-descriptions-item>
              <el-descriptions-item label="生成时间">
                {{ formatDateTime(artifact.created_at) }}
              </el-descriptions-item>
              <el-descriptions-item label="SHA-256" :span="2">
                <span class="approval-detail__hash">{{ artifact.sha256 }}</span>
              </el-descriptions-item>
            </el-descriptions>

            <div v-if="pending?.revision_comments?.length" class="approval-detail__comments">
              <div class="approval-detail__comments-title">
                历史修改意见（{{ pending.revision_comments.length }} 条，本轮之前）
              </div>
              <ol class="approval-detail__comment-list">
                <li v-for="(item, index) in pending.revision_comments" :key="index">{{ item }}</li>
              </ol>
            </div>
            <p v-else class="approval-detail__hint">本轮之前没有收到修改意见。</p>
          </template>
        </PageState>
      </el-card>

      <el-card shadow="never" class="approval-detail__card">
        <template #header>
          <div class="approval-detail__card-header">
            <span class="approval-detail__card-title">产物预览</span>
            <span class="approval-detail__card-note">
              内容通过后端下载接口读取；Markdown 与文本在页内渲染，PDF 由浏览器查看器显示，其他类型仅下载。
            </span>
          </div>
        </template>
        <ArtifactPreview
          :artifact="artifact"
          :metadata-loading="artifactLoading"
          empty-text="没有可预览的产物"
        />
      </el-card>

      <el-card shadow="never" class="approval-detail__card">
        <template #header>
          <div class="approval-detail__card-header">
            <span class="approval-detail__card-title">审批历史</span>
            <span class="approval-detail__card-count">共 {{ history.length }} 条</span>
          </div>
        </template>
        <PageState
          :empty="history.length === 0"
          empty-text="还没有审批记录"
          min-height="120px"
        >
          <el-table
            class="approval-history"
            :data="history"
            row-key="id"
            stripe
            style="width: 100%"
          >
            <el-table-column label="序号" prop="sequence" width="64" align="center" />
            <el-table-column label="结果" width="100" align="center">
              <template #default="{ row }">
                <StatusTag :status="row.decision" kind="decision" />
              </template>
            </el-table-column>
            <el-table-column label="审批人" width="150" show-overflow-tooltip>
              <template #default="{ row }">{{ row.approver }}</template>
            </el-table-column>
            <el-table-column label="意见" min-width="260" show-overflow-tooltip>
              <template #default="{ row }">{{ row.comment || '—' }}</template>
            </el-table-column>
            <el-table-column label="时间" width="160">
              <template #default="{ row }">{{ formatDateTime(row.created_at) }}</template>
            </el-table-column>
          </el-table>
          <p class="approval-detail__hint">
            审批历史只追加不修改：每条决定都保留在记录里，页面不提供编辑或删除。
          </p>
        </PageState>
      </el-card>

      <el-card v-if="isPending" shadow="never" class="approval-detail__card">
        <template #header>
          <span class="approval-detail__card-title">提交决定</span>
        </template>
        <p class="approval-detail__explain">
          通过：本轮产物被接受，运行进入完成。驳回：运行回到生成节点，按驳回理由产出下一轮产物并再次请求审批。
          两种决定都会写入审批历史，且需要二次确认。
        </p>
        <div class="approval-detail__decisions">
          <el-button
            type="primary"
            :loading="submitting"
            :disabled="submitting"
            @click="openDecision('approved')"
          >
            <el-icon><Check /></el-icon>
            <span>通过</span>
          </el-button>
          <el-button
            type="danger"
            plain
            :loading="submitting"
            :disabled="submitting"
            @click="openDecision('rejected')"
          >
            <el-icon><Close /></el-icon>
            <span>驳回</span>
          </el-button>
        </div>
      </el-card>

      <ApprovalDecisionDialog
        v-model="dialogVisible"
        :decision="decision"
        :workflow-short-id="shortId(workflow.id)"
        :artifact-name="artifactName"
        :submitting="submitting"
        @submit="handleDecision"
      />
    </template>
  </div>
</template>

<style scoped>
.approval-detail__alert {
  margin-bottom: 16px;
}

.approval-detail__card {
  margin-bottom: 16px;
}

.approval-detail__card-header {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

.approval-detail__card-title {
  font-size: 15px;
  font-weight: 600;
}

.approval-detail__card-count {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.approval-detail__card-note {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.approval-detail__card-action {
  margin-left: auto;
}

.approval-detail__artifact {
  margin-bottom: 12px;
}

.approval-detail__actions {
  display: flex;
  gap: 8px;
}

.approval-detail__code {
  margin-left: 6px;
  color: var(--el-text-color-secondary);
  font-size: 12px;
}

.approval-detail__raw {
  margin-left: 6px;
  color: var(--el-text-color-secondary);
  font-size: 12px;
}

.approval-detail__hash {
  font-family: var(--el-font-family-monospace, monospace);
  font-size: 12px;
  word-break: break-all;
}

.approval-detail__ellipsis {
  display: inline-block;
  max-width: 100%;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  vertical-align: bottom;
}

.approval-detail__comments {
  margin-top: 8px;
}

.approval-detail__comments-title {
  font-size: 13px;
  font-weight: 600;
  margin-bottom: 6px;
}

.approval-detail__comment-list {
  margin: 0;
  padding-left: 20px;
  color: var(--el-text-color-regular);
  font-size: 13px;
  line-height: 1.7;
}

.approval-detail__hint {
  margin: 8px 0 0;
  color: var(--el-text-color-secondary);
  font-size: 12px;
}

.approval-detail__explain {
  margin: 0 0 14px;
  color: var(--el-text-color-regular);
  font-size: 13px;
  line-height: 1.7;
}

.approval-detail__decisions {
  display: flex;
  gap: 12px;
}
</style>
