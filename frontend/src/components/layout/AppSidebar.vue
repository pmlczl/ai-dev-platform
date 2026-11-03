<script setup lang="ts">
import { useRoute } from 'vue-router'

import { useAppStore } from '@/stores'

const appStore = useAppStore()
const route = useRoute()

const menus = [
  { index: '/', title: '首页', icon: 'HomeFilled' },
  { index: '/workbench', title: '工作台', icon: 'Monitor' },
]
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
      :default-active="route.path"
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
