<script setup lang="ts">
/**
 * The header of a detail page.
 *
 * Every detail page starts the same way: a way back, the title of the object,
 * its status and the actions that apply to it.
 */
import { useRouter } from 'vue-router'
import type { RouteLocationRaw } from 'vue-router'

const props = withDefaults(
  defineProps<{
    title: string
    subtitle?: string | null
    /** Where the back button leads - without it the browser history is used. */
    backTo?: RouteLocationRaw | null
    backText?: string
  }>(),
  { subtitle: null, backTo: null, backText: '返回' },
)

const router = useRouter()

function handleBack(): void {
  if (props.backTo) {
    void router.push(props.backTo)
    return
  }
  router.back()
}
</script>

<template>
  <div class="page-header">
    <div class="page-header__main">
      <el-button class="page-header__back" text @click="handleBack">
        <el-icon><ArrowLeft /></el-icon>
        <span>{{ backText }}</span>
      </el-button>
      <div class="page-header__titles">
        <div class="page-header__title-row">
          <h2 class="page-header__title" :title="title">{{ title }}</h2>
          <slot name="tags" />
        </div>
        <div v-if="subtitle || $slots.subtitle" class="page-header__subtitle">
          <slot name="subtitle">{{ subtitle }}</slot>
        </div>
      </div>
    </div>
    <div v-if="$slots.actions" class="page-header__actions">
      <slot name="actions" />
    </div>
  </div>
</template>

<style scoped>
.page-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 16px;
}

.page-header__main {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  min-width: 0;
}

.page-header__back {
  padding: 6px 8px;
  margin-top: 2px;
  flex-shrink: 0;
}

.page-header__titles {
  min-width: 0;
}

.page-header__title-row {
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 0;
}

.page-header__title {
  margin: 0;
  font-size: 20px;
  font-weight: 600;
  line-height: 32px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.page-header__subtitle {
  margin-top: 2px;
  color: var(--el-text-color-secondary);
  font-size: 13px;
  line-height: 20px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.page-header__actions {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
  padding-top: 2px;
}
</style>
