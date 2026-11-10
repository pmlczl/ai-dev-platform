import { http } from './client'

import type {
  Page,
  TaskCreate,
  TaskPriority,
  TaskRead,
  TaskStatus,
  TaskUpdate,
  WorkflowRead,
} from '@/types'

/** Filters of the task list. */
export interface TaskListParams {
  page?: number
  page_size?: number
  project_id?: string
  status?: TaskStatus
  priority?: TaskPriority
  keyword?: string
}

/** Fetch one page of the tasks. */
export async function fetchTasks(
  params: TaskListParams = {},
): Promise<Page<TaskRead>> {
  const { data } = await http.get<Page<TaskRead>>('/tasks', { params })
  return data
}

/** Fetch the details of one task. */
export async function fetchTask(taskId: string): Promise<TaskRead> {
  const { data } = await http.get<TaskRead>(`/tasks/${taskId}`)
  return data
}

/** Create a task inside a project. */
export async function createTask(payload: TaskCreate): Promise<TaskRead> {
  const { data } = await http.post<TaskRead>('/tasks', payload)
  return data
}

/** Update a task - only the fields that are present are written. */
export async function updateTask(
  taskId: string,
  payload: TaskUpdate,
): Promise<TaskRead> {
  const { data } = await http.put<TaskRead>(`/tasks/${taskId}`, payload)
  return data
}

/**
 * Fetch the workflow runs of one task.
 *
 * The list contains the runs that already ended as well - the history of a
 * task is part of its answer.
 */
export async function fetchTaskWorkflows(
  taskId: string,
  params: { page?: number; page_size?: number } = {},
): Promise<Page<WorkflowRead>> {
  const { data } = await http.get<Page<WorkflowRead>>(`/tasks/${taskId}/workflows`, {
    params,
  })
  return data
}
