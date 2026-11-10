import { createRouter, createWebHistory } from 'vue-router'
import type { RouteRecordRaw } from 'vue-router'

declare module 'vue-router' {
  interface RouteMeta {
    /** The title of the page - it is shown in the navigation and in the tab. */
    title?: string
    /** The name of the icon of the navigation entry. */
    icon?: string
    /** A detail route that has no own entry in the navigation. */
    hideInMenu?: boolean
    /** The navigation entry that stays active while this route is open. */
    activeMenu?: string
  }
}

const routes: RouteRecordRaw[] = [
  {
    path: '/',
    name: 'home',
    component: () => import('@/views/HomeView.vue'),
    meta: { title: '首页', icon: 'HomeFilled' },
  },
  {
    path: '/workbench',
    name: 'workbench',
    component: () => import('@/views/WorkbenchView.vue'),
    meta: { title: '工作台', icon: 'Monitor' },
  },
  {
    // The project list is the entry point of the project management.
    path: '/projects',
    name: 'projects',
    component: () => import('@/views/projects/ProjectListView.vue'),
    meta: { title: '项目管理', icon: 'FolderOpened' },
  },
  {
    path: '/projects/:project_id',
    name: 'project-detail',
    component: () => import('@/views/projects/ProjectDetailView.vue'),
    meta: { title: '项目详情', hideInMenu: true, activeMenu: '/projects' },
  },
  {
    path: '/tasks/:task_id',
    name: 'task-detail',
    component: () => import('@/views/tasks/TaskDetailView.vue'),
    meta: { title: '任务详情', hideInMenu: true },
  },
  {
    // The monitoring of the runs has its own entry: it stays reachable even
    // when a task detail page shows the state of a run as well.
    path: '/workflows',
    name: 'workflows',
    component: () => import('@/views/workflows/WorkflowListView.vue'),
    meta: { title: '工作流监控', icon: 'Connection' },
  },
  {
    path: '/approvals',
    name: 'approvals',
    component: () => import('@/views/approvals/ApprovalQueueView.vue'),
    meta: { title: '人工审批', icon: 'Stamp' },
  },
  {
    path: '/:pathMatch(.*)*',
    name: 'not-found',
    component: () => import('@/views/NotFoundView.vue'),
    meta: { title: '页面不存在', hideInMenu: true },
  },
]

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes,
})

router.afterEach((to) => {
  const title = (to.meta.title as string | undefined) ?? ''
  document.title = title ? `${title} · ${import.meta.env.VITE_APP_TITLE ?? 'AI Dev Platform'}` : 'AI Dev Platform'
})

export default router
