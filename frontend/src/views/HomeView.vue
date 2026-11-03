<script setup lang="ts">
import { onMounted } from 'vue'
import { useRouter } from 'vue-router'

import { useAppStore } from '@/stores'

const appStore = useAppStore()
const router = useRouter()

onMounted(async () => {
  await appStore.refreshBackendStatus()
  await appStore.refreshReadiness()
})
</script>

<template>
  <div class="home">
    <el-card shadow="never" class="home__hero">
      <h1 class="home__title">欢迎使用 {{ appStore.appTitle }}</h1>
      <p class="home__subtitle">
        前后端分离的模块化单体基础工程：FastAPI + SQLAlchemy 2.x + Alembic +
        Vue 3 + TypeScript + Element Plus + LangGraph 工作流骨架。
      </p>
      <el-space>
        <el-button type="primary" @click="router.push('/workbench')">进入工作台</el-button>
        <el-button @click="router.push('/workbench')">查看占位页面</el-button>
      </el-space>
    </el-card>

    <el-row :gutter="16" class="home__stats">
      <el-col :xs="24" :sm="12" :md="6">
        <el-card shadow="never">
          <div class="stat__label">后端状态</div>
          <div class="stat__value">
            {{ appStore.backendOnline === null ? '检测中' : appStore.backendOnline ? '正常' : '不可用' }}
          </div>
        </el-card>
      </el-col>
      <el-col :xs="24" :sm="12" :md="6">
        <el-card shadow="never">
          <div class="stat__label">服务版本</div>
          <div class="stat__value">{{ appStore.health?.version ?? '-' }}</div>
        </el-card>
      </el-col>
      <el-col :xs="24" :sm="12" :md="6">
        <el-card shadow="never">
          <div class="stat__label">运行环境</div>
          <div class="stat__value">{{ appStore.health?.environment ?? '-' }}</div>
        </el-card>
      </el-col>
      <el-col :xs="24" :sm="12" :md="6">
        <el-card shadow="never">
          <div class="stat__label">数据库</div>
          <div class="stat__value">
            {{ appStore.readiness?.database.status ?? '-' }}
            <span v-if="appStore.readiness?.database.latency_ms != null" class="stat__hint">
              ({{ appStore.readiness.database.latency_ms }} ms)
            </span>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <el-card shadow="never" class="home__notes">
      <template #header>当前阶段</template>
      <ul class="home__notes-list">
        <li>基础工程已就绪：配置、日志、异常、CORS、API 文档、健康检查。</li>
        <li>Alembic 迁移链路已接入，模型与业务表将在后续阶段补充。</li>
        <li>workflows / agents 目录仅保留抽象，AI Agent 业务功能尚未实现。</li>
      </ul>
    </el-card>
  </div>
</template>

<style scoped>
.home {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.home__title {
  margin: 0 0 8px;
  font-size: 22px;
}

.home__subtitle {
  margin: 0 0 16px;
  color: var(--el-text-color-secondary);
  line-height: 1.7;
}

.stat__label {
  color: var(--el-text-color-secondary);
  font-size: 13px;
}

.stat__value {
  margin-top: 6px;
  font-size: 18px;
  font-weight: 600;
}

.stat__hint {
  font-size: 12px;
  font-weight: 400;
  color: var(--el-text-color-secondary);
}

.home__notes-list {
  margin: 0;
  padding-left: 18px;
  line-height: 2;
  color: var(--el-text-color-regular);
}
</style>
