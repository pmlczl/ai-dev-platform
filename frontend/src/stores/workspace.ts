import { ref } from 'vue'
import { defineStore } from 'pinia'

import { fetchProject } from '@/api/projects'
import { fetchTask } from '@/api/tasks'
import { fetchWorkflow } from '@/api/workflows'

import type { ProjectRead, TaskRead, WorkflowRead } from '@/types'

/**
 * The context of the page the user is looking at.
 *
 * The store remembers which project, task and workflow are open, so a page
 * can navigate from one to the other. It is a cache and never the only
 * source of a value: every object can be loaded again from the API with its
 * id, and a page that is opened directly always loads its data from the
 * backend.
 */
export const useWorkspaceStore = defineStore('workspace', () => {
  const projectId = ref<string | null>(null)
  const taskId = ref<string | null>(null)
  const workflowId = ref<string | null>(null)

  const project = ref<ProjectRead | null>(null)
  const task = ref<TaskRead | null>(null)
  const workflow = ref<WorkflowRead | null>(null)

  /** Set the project that is open. */
  function focusProject(id: string | null): void {
    projectId.value = id
    if (id === null) {
      project.value = null
    }
  }

  /** Set the task that is open. */
  function focusTask(id: string | null): void {
    taskId.value = id
    if (id === null) {
      task.value = null
    }
  }

  /** Set the workflow that is open. */
  function focusWorkflow(id: string | null): void {
    workflowId.value = id
    if (id === null) {
      workflow.value = null
    }
  }

  /** Forget everything. */
  function reset(): void {
    projectId.value = null
    taskId.value = null
    workflowId.value = null
    project.value = null
    task.value = null
    workflow.value = null
  }

  /**
   * Load the objects of the current context again.
   *
   * A failing request leaves the object empty - it never keeps an old value
   * that does not exist any more.
   */
  async function reload(): Promise<void> {
    project.value = projectId.value ? await fetchProject(projectId.value) : null
    task.value = taskId.value ? await fetchTask(taskId.value) : null
    workflow.value = workflowId.value ? await fetchWorkflow(workflowId.value) : null
  }

  return {
    projectId,
    taskId,
    workflowId,
    project,
    task,
    workflow,
    focusProject,
    focusTask,
    focusWorkflow,
    reset,
    reload,
  }
})
