<script setup lang="ts">
import AppHeader from '@/components/layout/AppHeader.vue'
import AppSidebar from '@/components/layout/AppSidebar.vue'
</script>

<template>
  <el-container class="app-layout">
    <AppSidebar />
    <el-container class="app-layout__body">
      <AppHeader />
      <el-main class="app-layout__main">
        <router-view />
      </el-main>
    </el-container>
  </el-container>
</template>

<style scoped>
.app-layout {
  height: 100vh;
}

.app-layout__body {
  min-width: 0;
}

.app-layout__main {
  background-color: var(--el-bg-color-page);
  padding: 16px;
}
</style>
