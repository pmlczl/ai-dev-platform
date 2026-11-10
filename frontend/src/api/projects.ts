import { http } from './client'

import type {
  Page,
  ProjectCreate,
  ProjectListItem,
  ProjectRead,
  ProjectStatus,
  ProjectUpdate,
  TaskRead,
  TaskStatus,
} from '@/types'

/** Filters of the project list. */
export interface ProjectListParams {
  page?: number
  page_size?: number
  status?: ProjectStatus
  keyword?: string
}

/** Fetch one page of the projects. */
export async function fetchProjects(
  params: ProjectListParams = {},
): Promise<Page<ProjectListItem>> {
  const { data } = await http.get<Page<ProjectListItem>>('/projects', { params })
  return data
}

/** Fetch the details of one project. */
export async function fetchProject(projectId: string): Promise<ProjectRead> {
  const { data } = await http.get<ProjectRead>(`/projects/${projectId}`)
  return data
}

/** Create a project. */
export async function createProject(payload: ProjectCreate): Promise<ProjectRead> {
  const { data } = await http.post<ProjectRead>('/projects', payload)
  return data
}

/** Update a project - only the fields that are present are written. */
export async function updateProject(
  projectId: string,
  payload: ProjectUpdate,
): Promise<ProjectRead> {
  const { data } = await http.put<ProjectRead>(`/projects/${projectId}`, payload)
  return data
}

/** Delete a project - the backend removes it softly. */
export async function deleteProject(projectId: string): Promise<void> {
  await http.delete(`/projects/${projectId}`)
}

/** Filters of the task list of a project. */
export interface ProjectTaskListParams {
  page?: number
  page_size?: number
  status?: TaskStatus
}

/** Fetch one page of the tasks of a project. */
export async function fetchProjectTasks(
  projectId: string,
  params: ProjectTaskListParams = {},
): Promise<Page<TaskRead>> {
  const { data } = await http.get<Page<TaskRead>>(`/projects/${projectId}/tasks`, {
    params,
  })
  return data
}
