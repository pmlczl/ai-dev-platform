<script setup lang="ts">
import { useAppStore } from '@/stores'

const appStore = useAppStore()
</script>

<template>
  <el-card shadow="never">
    <el-empty description="工作台（占位页面，AI Agent 业务功能将在后续阶段实现）">
      <el-space direction="vertical">
        <el-tag type="info" effect="plain">后端版本：{{ appStore.health?.version ?? '-' }}</el-tag>
        <el-tag type="info" effect="plain">工作流目录已预留，尚未接入实际 Agent</el-tag>
      </el-space>
    </el-empty>
  </el-card>
</template>
