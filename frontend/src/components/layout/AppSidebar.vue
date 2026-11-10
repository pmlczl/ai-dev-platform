<script setup lang="ts">
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { useAppStore } from '@/stores'

const appStore = useAppStore()
const route = useRoute()
const router = useRouter()

/**
 * The navigation is built from the routing table.
 *
 * A page that is added to the router shows up here - the menu never has to
 * be maintained a second time.
 */
const menus = computed(() =>
  router
    .getRoutes()
    .filter((item) => Boolean(item.meta?.title) && !item.meta?.hideInMenu)
    .map((item) => ({
      index: item.path,
      title: item.meta.title as string,
      icon: (item.meta.icon as string | undefined) ?? 'Menu',
    })),
)

/**
 * The entry that stays highlighted.
 *
 * A detail route points to the entry it belongs to - the project detail
 * keeps the project management highlighted.
 */
const activeMenu = computed(() => {
  const explicit = route.meta?.activeMenu
  if (typeof explicit === 'string') {
    return explicit
  }
  const match = menus.value.find(
    (menu) => route.path === menu.index || route.path.startsWith(`${menu.index}/`),
  )
  return match?.index ?? route.path
})
</script>

<template>
  <el-aside
    class="app-sidebar"
    :width="appStore.sidebarCollapsed ? '64px' : '220px'"
  >
    <div class="app-sidebar__logo">
      <el-icon class="app-sidebar__logo-icon"><Platform /></el-icon>
      <span v-show="!appStore.sidebarCollapsed" class="app-sidebar__logo-text">
        {{ appStore.appTitle }}
      </span>
    </div>

    <el-menu
      class="app-sidebar__menu"
      :default-active="activeMenu"
      :collapse="appStore.sidebarCollapsed"
      :collapse-transition="false"
      router
    >
      <el-menu-item v-for="menu in menus" :key="menu.index" :index="menu.index">
        <el-icon><component :is="menu.icon" /></el-icon>
        <template #title>{{ menu.title }}</template>
      </el-menu-item>
    </el-menu>
  </el-aside>
</template>

<style scoped>
.app-sidebar {
  background-color: var(--el-bg-color);
  border-right: 1px solid var(--el-border-color-lighter);
  transition: width 0.2s ease;
  overflow-x: hidden;
}

.app-sidebar__logo {
  display: flex;
  align-items: center;
  gap: 10px;
  height: 60px;
  padding: 0 20px;
  font-size: 16px;
  font-weight: 600;
  white-space: nowrap;
  border-bottom: 1px solid var(--el-border-color-lighter);
}

.app-sidebar__logo-icon {
  font-size: 22px;
  color: var(--el-color-primary);
}

.app-sidebar__menu {
  border-right: none;
}
</style>
