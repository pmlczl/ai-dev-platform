<script setup lang="ts">
/**
 * The three states of a page that loads data.
 *
 * Every list and every detail view renders its content through this
 * component, so a page never has to write the loading, the empty and the
 * error case on its own.
 */
withDefaults(
  defineProps<{
    /** The data is being loaded. */
    loading?: boolean
    /** The load failed - the text is shown to the user. */
    error?: string | null
    /** The request succeeded but there is nothing to show. */
    empty?: boolean
    emptyText?: string
    loadingText?: string
    /** The minimum height of the state, so the layout does not jump. */
    minHeight?: string
  }>(),
  {
    loading: false,
    error: null,
    empty: false,
    emptyText: '暂无数据',
    loadingText: '加载中…',
    minHeight: '160px',
  },
)
</script>

<template>
  <div v-if="loading" class="page-state" :style="{ minHeight }">
    <el-icon class="page-state__icon is-loading"><Loading /></el-icon>
    <p class="page-state__text">{{ loadingText }}</p>
  </div>

  <div v-else-if="error" class="page-state page-state--error" :style="{ minHeight }">
    <el-icon class="page-state__icon"><WarningFilled /></el-icon>
    <p class="page-state__text">{{ error }}</p>
    <slot name="error" />
  </div>

  <div v-else-if="empty" class="page-state page-state--empty" :style="{ minHeight }">
    <el-icon class="page-state__icon"><DocumentDelete /></el-icon>
    <p class="page-state__text">{{ emptyText }}</p>
    <slot name="empty" />
  </div>

  <div v-else class="page-state__content">
    <slot />
  </div>
</template>

<style scoped>
.page-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 10px;
  width: 100%;
  color: var(--el-text-color-secondary);
  text-align: center;
}

.page-state__icon {
  font-size: 30px;
  color: var(--el-text-color-placeholder);
}

.page-state--error .page-state__icon {
  color: var(--el-color-danger);
}

.page-state__text {
  margin: 0;
  font-size: 14px;
  line-height: 1.6;
  white-space: pre-wrap;
  word-break: break-word;
}

.page-state__content {
  width: 100%;
}
</style>
