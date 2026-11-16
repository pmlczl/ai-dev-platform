<script setup lang="ts">
/**
 * The path of a workflow run through the nodes of its graph.
 *
 * The nodes are the ones of `backend/app/workflows/dev_workflow.py`; which
 * node is current and which ones were passed is read from the run and from
 * its event log only. The component never guesses a state: a node that no
 * event mentions is pending, whatever its position in the path.
 */
import { computed } from 'vue'

import {
  WORKFLOW_BRANCH_NODES,
  WORKFLOW_MAIN_PATH,
  isWorkflowLive,
  workflowNodeLabel,
} from '@/constants/workflow'

import type { WorkflowNodeInfo } from '@/constants/workflow'
import type { WorkflowEventRead, WorkflowRead } from '@/types'

const props = defineProps<{
  workflow: WorkflowRead
  /** The events of the run - the whole log, oldest first. */
  events: WorkflowEventRead[]
}>()

type NodeState = 'completed' | 'current' | 'waiting' | 'failed' | 'pending'

interface NodeView extends WorkflowNodeInfo {
  state: NodeState
  /** How often the node was entered - a revision loop enters a node again. */
  visits: number
}

const STATE_LABELS: Record<NodeState, string> = {
  completed: '已完成',
  current: '进行中',
  waiting: '等待审批',
  failed: '失败',
  pending: '未开始',
}

/**
 * How often every step was entered.
 *
 * Not every node writes a `node_started` event, so an entry is counted when
 * the step of the log changes: a revision loop that comes back to a node
 * counts as a second entry.
 */
const visits = computed<Record<string, number>>(() => {
  const result: Record<string, number> = {}
  let previous: string | null = null
  for (const event of props.events) {
    if (event.step !== previous) {
      result[event.step] = (result[event.step] ?? 0) + 1
      previous = event.step
    }
  }
  return result
})

/** The step at which the run failed - the one of the `workflow_failed` event. */
const failedStep = computed<string | null>(() => {
  for (let index = props.events.length - 1; index >= 0; index -= 1) {
    const event = props.events[index]
    if (event.event === 'workflow_failed') {
      return event.step
    }
  }
  return props.workflow.status === 'failed' ? props.workflow.current_step : null
})

function stateOf(key: string): NodeState {
  const run = props.workflow
  const visited = (visits.value[key] ?? 0) > 0
  if (run.status === 'failed') {
    if (key === failedStep.value || (key === 'fail_workflow' && visited)) {
      return 'failed'
    }
    return visited ? 'completed' : 'pending'
  }
  if (isWorkflowLive(run.status) && key === run.current_step) {
    return run.status === 'waiting_approval' ? 'waiting' : 'current'
  }
  if (run.status === 'completed' && key === 'complete_workflow') {
    return 'completed'
  }
  return visited ? 'completed' : 'pending'
}

const mainNodes = computed<NodeView[]>(() =>
  WORKFLOW_MAIN_PATH.map((node) => ({
    ...node,
    state: stateOf(node.key),
    visits: visits.value[node.key] ?? 0,
  })),
)

/** The branch nodes the run went through - they are shown only when they occurred. */
const branchNodes = computed<NodeView[]>(() => {
  const keys = new Set<string>()
  for (const event of props.events) {
    if (WORKFLOW_BRANCH_NODES[event.step]) {
      keys.add(event.step)
    }
  }
  const current = props.workflow.current_step
  if (current && WORKFLOW_BRANCH_NODES[current]) {
    keys.add(current)
  }
  return [...keys].map((key) => {
    const info = WORKFLOW_BRANCH_NODES[key] ?? {
      key,
      label: workflowNodeLabel(key),
      description: '',
    }
    return { ...info, state: stateOf(key), visits: visits.value[key] ?? 0 }
  })
})

/** A node the backend names that the graph here does not know. */
const unknownCurrent = computed(() => {
  const current = props.workflow.current_step
  if (!current) {
    return null
  }
  const known =
    WORKFLOW_MAIN_PATH.some((node) => node.key === current) ||
    Boolean(WORKFLOW_BRANCH_NODES[current])
  return known ? null : current
})
</script>

<template>
  <div class="node-path">
    <ol class="node-path__list">
      <li class="node-path__start">
        <span class="node-path__start-dot" />
        <span class="node-path__start-label">START</span>
      </li>
      <li
        v-for="node in mainNodes"
        :key="node.key"
        class="node-path__item"
        :class="`node-path__item--${node.state}`"
        :data-node="node.key"
        :data-state="node.state"
      >
        <el-tooltip :content="node.description" placement="top">
          <div class="node-path__node">
            <span class="node-path__marker">
              <el-icon v-if="node.state === 'completed'"><Check /></el-icon>
              <el-icon v-else-if="node.state === 'failed'"><Close /></el-icon>
              <el-icon v-else-if="node.state === 'current'" class="is-loading"><Loading /></el-icon>
              <el-icon v-else-if="node.state === 'waiting'"><Clock /></el-icon>
              <span v-else class="node-path__marker-dot" />
            </span>
            <span class="node-path__label">{{ node.label }}</span>
            <span class="node-path__state">
              {{ STATE_LABELS[node.state] }}<template v-if="node.visits > 1"> · {{ node.visits }} 次</template>
            </span>
          </div>
        </el-tooltip>
      </li>
    </ol>

    <div v-if="branchNodes.length > 0 || unknownCurrent" class="node-path__branches">
      <span class="node-path__branches-title">本次运行经过的分支节点</span>
      <div class="node-path__branch-list">
        <div
          v-for="node in branchNodes"
          :key="node.key"
          class="node-path__branch"
          :class="`node-path__item--${node.state}`"
          :data-node="node.key"
          :data-state="node.state"
        >
          <span class="node-path__marker">
            <el-icon v-if="node.state === 'completed'"><Check /></el-icon>
            <el-icon v-else-if="node.state === 'failed'"><Close /></el-icon>
            <el-icon v-else-if="node.state === 'current'" class="is-loading"><Loading /></el-icon>
            <span v-else class="node-path__marker-dot" />
          </span>
          <span class="node-path__label">{{ node.label }}</span>
          <span class="node-path__state">
            {{ STATE_LABELS[node.state] }}<template v-if="node.visits > 1"> · {{ node.visits }} 次</template>
          </span>
          <span v-if="node.description" class="node-path__branch-desc">{{ node.description }}</span>
        </div>
        <div v-if="unknownCurrent" class="node-path__branch node-path__item--current">
          <span class="node-path__label">{{ unknownCurrent }}</span>
          <span class="node-path__state">后端报告的当前节点（前端未登记该节点）</span>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.node-path__list {
  display: flex;
  align-items: stretch;
  gap: 0;
  margin: 0;
  padding: 0;
  list-style: none;
  overflow-x: auto;
}

.node-path__start {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 4px;
  min-width: 64px;
  color: var(--el-text-color-secondary);
  font-size: 12px;
}

.node-path__start-dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  background: var(--el-text-color-placeholder);
}

.node-path__item {
  position: relative;
  display: flex;
  flex: 1 1 0;
  min-width: 150px;
  padding: 0 8px;
}

.node-path__item::before {
  content: '';
  position: absolute;
  top: 22px;
  left: -50%;
  width: 100%;
  height: 2px;
  background: var(--el-border-color);
  z-index: 0;
}

.node-path__item--completed::before {
  background: var(--el-color-success);
}

.node-path__item--current::before,
.node-path__item--waiting::before {
  background: var(--el-color-primary);
}

.node-path__item--failed::before {
  background: var(--el-color-danger);
}

.node-path__node {
  position: relative;
  z-index: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
  width: 100%;
  padding: 8px 6px 10px;
  border: 1px solid var(--el-border-color);
  border-radius: 6px;
  background: var(--el-bg-color);
  text-align: center;
}

.node-path__marker {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  border-radius: 50%;
  border: 2px solid var(--el-border-color);
  color: var(--el-text-color-secondary);
  background: var(--el-bg-color);
}

.node-path__marker-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--el-border-color);
}

.node-path__item--completed .node-path__marker {
  border-color: var(--el-color-success);
  color: #fff;
  background: var(--el-color-success);
}

.node-path__item--completed .node-path__node {
  border-color: var(--el-color-success-light-5);
}

.node-path__item--current .node-path__marker {
  border-color: var(--el-color-primary);
  color: var(--el-color-primary);
}

.node-path__item--current .node-path__node {
  border-color: var(--el-color-primary);
  background: var(--el-color-primary-light-9);
}

.node-path__item--waiting .node-path__marker {
  border-color: var(--el-color-warning);
  color: #fff;
  background: var(--el-color-warning);
}

.node-path__item--waiting .node-path__node {
  border-color: var(--el-color-warning);
  background: var(--el-color-warning-light-9);
}

.node-path__item--failed .node-path__marker {
  border-color: var(--el-color-danger);
  color: #fff;
  background: var(--el-color-danger);
}

.node-path__item--failed .node-path__node {
  border-color: var(--el-color-danger);
  background: var(--el-color-danger-light-9);
}

.node-path__label {
  font-size: 13px;
  font-weight: 600;
}

.node-path__state {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.node-path__item--current .node-path__state {
  color: var(--el-color-primary);
}

.node-path__item--waiting .node-path__state {
  color: var(--el-color-warning-dark-2, var(--el-color-warning));
}

.node-path__item--failed .node-path__state {
  color: var(--el-color-danger);
}

.node-path__branches {
  margin-top: 16px;
  padding-top: 12px;
  border-top: 1px dashed var(--el-border-color-lighter);
}

.node-path__branches-title {
  display: block;
  margin-bottom: 8px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.node-path__branch-list {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.node-path__branch {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 6px 12px;
  border: 1px solid var(--el-border-color);
  border-radius: 6px;
  background: var(--el-bg-color);
}

.node-path__branch .node-path__marker {
  width: 22px;
  height: 22px;
  font-size: 12px;
}

.node-path__branch-desc {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
</style>
