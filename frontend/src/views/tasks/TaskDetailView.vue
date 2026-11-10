<script setup lang="ts">
import { useRoute } from 'vue-router'

/**
 * Placeholder of the task detail.
 *
 * The page is built in M4; the route exists since M0 so that a task can be
 * opened directly by its id.
 */
const route = useRoute()
</script>

<template>
  <el-card shadow="never">
    <el-empty :description="`任务详情（页面在 M4 实现）· 任务 ${route.params.task_id ?? '-'}`" />
  </el-card>
</template>
