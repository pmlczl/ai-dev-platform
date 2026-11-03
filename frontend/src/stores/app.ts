import { computed, ref } from 'vue'
import { defineStore } from 'pinia'

import { fetchHealth, fetchReadiness } from '@/api/health'
import type { HealthInfo, ReadinessInfo } from '@/api/health'

/**
 * Global application state: layout preferences and the backend status shown
 * in the top navigation bar.
 */
export const useAppStore = defineStore('app', () => {
  const sidebarCollapsed = ref(false)
  const health = ref<HealthInfo | null>(null)
  const readiness = ref<ReadinessInfo | null>(null)
  const backendOnline = ref<boolean | null>(null)

  const appTitle = computed(() => import.meta.env.VITE_APP_TITLE ?? 'AI Dev Platform')

  function toggleSidebar(): void {
    sidebarCollapsed.value = !sidebarCollapsed.value
  }

  async function refreshBackendStatus(): Promise<void> {
    try {
      health.value = await fetchHealth()
      backendOnline.value = health.value.status === 'ok'
    } catch {
      health.value = null
      backendOnline.value = false
    }
  }

  async function refreshReadiness(): Promise<void> {
    try {
      readiness.value = await fetchReadiness()
    } catch {
      readiness.value = null
    }
  }

  return {
    appTitle,
    sidebarCollapsed,
    health,
    readiness,
    backendOnline,
    toggleSidebar,
    refreshBackendStatus,
    refreshReadiness,
  }
})
