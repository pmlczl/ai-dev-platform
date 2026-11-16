import { reactive } from 'vue'
import { defineStore } from 'pinia'

import { fetchProject } from '@/api/projects'
import { fetchTask } from '@/api/tasks'

import type { ProjectRead, TaskRead } from '@/types'

/**
 * A cache of the names behind the ids the backend sends.
 *
 * `WorkflowRead` carries `project_id` and `task_id` only. A page that lists
 * runs therefore resolves the names it shows through this store: an id is
 * fetched once, every later row and every poll reads the cached value. The
 * store never invents a name - until the backend answered, a page shows the
 * id.
 *
 * The cache is seeded by every list the pages already loaded (a task table,
 * a project detail), so most lookups never hit the network.
 */
export const useReferenceStore = defineStore('reference', () => {
  const projects = reactive<Record<string, ProjectRead>>({})
  const tasks = reactive<Record<string, TaskRead>>({})
  /** Ids whose lookup failed - they are not retried on every poll. */
  const missingProjects = reactive(new Set<string>())
  const missingTasks = reactive(new Set<string>())
  const inflight = new Map<string, Promise<void>>()

  /** Remember projects a page already loaded. */
  function rememberProjects(items: ProjectRead[]): void {
    for (const item of items) {
      projects[item.id] = item
      missingProjects.delete(item.id)
    }
  }

  /** Remember tasks a page already loaded. */
  function rememberTasks(items: TaskRead[]): void {
    for (const item of items) {
      tasks[item.id] = item
      missingTasks.delete(item.id)
    }
  }

  function load(key: string, loader: () => Promise<void>): Promise<void> {
    const running = inflight.get(key)
    if (running) {
      return running
    }
    const promise = loader().finally(() => inflight.delete(key))
    inflight.set(key, promise)
    return promise
  }

  /** Fetch the projects that are not cached yet. */
  async function resolveProjects(ids: Array<string | null | undefined>): Promise<void> {
    const wanted = [...new Set(ids.filter((id): id is string => Boolean(id)))].filter(
      (id) => !projects[id] && !missingProjects.has(id),
    )
    await Promise.all(
      wanted.map((id) =>
        load(`project:${id}`, async () => {
          try {
            projects[id] = await fetchProject(id, { silent: true })
          } catch {
            missingProjects.add(id)
          }
        }),
      ),
    )
  }

  /** Fetch the tasks that are not cached yet. */
  async function resolveTasks(ids: Array<string | null | undefined>): Promise<void> {
    const wanted = [...new Set(ids.filter((id): id is string => Boolean(id)))].filter(
      (id) => !tasks[id] && !missingTasks.has(id),
    )
    await Promise.all(
      wanted.map((id) =>
        load(`task:${id}`, async () => {
          try {
            tasks[id] = await fetchTask(id, { silent: true })
          } catch {
            missingTasks.add(id)
          }
        }),
      ),
    )
  }

  /** Forget a failed lookup so it is tried again. */
  function forgetMissing(): void {
    missingProjects.clear()
    missingTasks.clear()
  }

  return {
    projects,
    tasks,
    missingProjects,
    missingTasks,
    rememberProjects,
    rememberTasks,
    resolveProjects,
    resolveTasks,
    forgetMissing,
  }
})
