<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { useAppStore } from '@/stores'

const appStore = useAppStore()
const route = useRoute()
const router = useRouter()
const loading = ref(false)

/**
 * The trail of the page.
 *
 * A detail route names the navigation entry it belongs to (`meta.activeMenu`),
 * so the trail shows that entry before the title of the page itself.
 */
const trail = computed(() => {
  const items: Array<{ title: string; to: string | null }> = []
  if (route.path === '/') {
    return items
  }
  const parentPath = route.meta.activeMenu
  if (typeof parentPath === 'string' && parentPath !== route.path) {
    const parent = router.getRoutes().find((item) => item.path === parentPath)
    if (parent?.meta.title) {
      items.push({ title: parent.meta.title as string, to: parentPath })
    }
  }
  items.push({ title: (route.meta.title as string | undefined) ?? '', to: null })
  return items
})

onMounted(async () => {
  await appStore.refreshBackendStatus()
})

async function handleRefresh(): Promise<void> {
  loading.value = true
  try {
    await appStore.refreshBackendStatus()
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <el-header class="app-header">
    <div class="app-header__left">
      <el-button text class="app-header__toggle" @click="appStore.toggleSidebar()">
        <el-icon size="18">
          <component :is="appStore.sidebarCollapsed ? 'Expand' : 'Fold'" />
        </el-icon>
      </el-button>
      <el-breadcrumb separator="/">
        <el-breadcrumb-item :to="{ path: '/' }">首页</el-breadcrumb-item>
        <el-breadcrumb-item
          v-for="item in trail"
          :key="item.title"
          :to="item.to ? { path: item.to } : undefined"
        >
          {{ item.title }}
        </el-breadcrumb-item>
      </el-breadcrumb>
    </div>

    <div class="app-header__right">
      <el-tag
        :type="appStore.backendOnline === null ? 'info' : appStore.backendOnline ? 'success' : 'danger'"
        effect="light"
      >
        后端 {{ appStore.backendOnline === null ? '检测中' : appStore.backendOnline ? '正常' : '不可用' }}
      </el-tag>
      <el-button text :loading="loading" @click="handleRefresh">
        <el-icon><Refresh /></el-icon>
      </el-button>
    </div>
  </el-header>
</template>

<style scoped>
.app-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  height: 60px;
  padding: 0 20px;
  background-color: var(--el-bg-color);
  border-bottom: 1px solid var(--el-border-color-lighter);
}

.app-header__left,
.app-header__right {
  display: flex;
  align-items: center;
  gap: 12px;
}

.app-header__toggle {
  font-size: 18px;
}
</style>
