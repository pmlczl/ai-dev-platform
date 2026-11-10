<script setup lang="ts">
import { useRoute } from 'vue-router'

/**
 * Placeholder of the project detail.
 *
 * The page is built in M2; the route exists since M0 so that a project can
 * be opened directly by its id.
 */
const route = useRoute()
</script>

<template>
  <el-card shadow="never">
    <el-empty :description="`项目详情（页面在 M2 实现）· 项目 ${route.params.project_id ?? '-'}`" />
  </el-card>
</template>
