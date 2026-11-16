<script setup lang="ts">
/**
 * The search bar of the project list.
 *
 * The component owns the text of the keyword field and the delay before it is
 * applied; the page receives the result and turns it into a request.
 */
import { onBeforeUnmount, ref, watch } from 'vue'
import { Search } from '@element-plus/icons-vue'

import { PROJECT_STATUS_OPTIONS } from '@/constants/status'

import type { ProjectStatus } from '@/types'

/** How long the user has to stop typing before the keyword is applied. */
const DEBOUNCE_MS = 300

const props = withDefaults(
  defineProps<{
    /** The keyword that is currently applied. */
    keyword?: string
    /** The status that is currently applied - an empty value means "all". */
    status?: ProjectStatus | ''
    /** The list is being loaded. */
    loading?: boolean
  }>(),
  { keyword: '', status: '', loading: false },
)

const emit = defineEmits<{
  /** The applied filters changed - the page reloads the list. */
  (event: 'search', payload: { keyword: string; status: ProjectStatus | '' }): void
  /** The user asked for the list to be loaded again. */
  (event: 'refresh'): void
}>()

/** The text of the input - it may differ from the applied keyword. */
const keywordInput = ref(props.keyword)

let timer: ReturnType<typeof setTimeout> | null = null

watch(
  () => props.keyword,
  (value) => {
    // The input is only overwritten when the keyword comes from the outside -
    // a click on "back" for example - and the user is not typing.
    if (timer === null && value.trim() !== keywordInput.value.trim()) {
      keywordInput.value = value
    }
  },
)

/** Apply the keyword after the user stopped typing. */
function handleInput(value: string): void {
  keywordInput.value = value
  if (timer !== null) {
    clearTimeout(timer)
  }
  timer = setTimeout(() => {
    timer = null
    emit('search', { keyword: value.trim(), status: props.status })
  }, DEBOUNCE_MS)
}

/** Apply the status - it is chosen, not typed, so it needs no delay. */
function handleStatus(value: ProjectStatus | ''): void {
  emit('search', { keyword: keywordInput.value.trim(), status: value })
}

/** Clear the keyword. */
function handleClear(): void {
  keywordInput.value = ''
  if (timer !== null) {
    clearTimeout(timer)
    timer = null
  }
  emit('search', { keyword: '', status: props.status })
}

onBeforeUnmount(() => {
  if (timer !== null) {
    clearTimeout(timer)
  }
})
</script>

<template>
  <div class="project-search">
    <el-input
      v-model="keywordInput"
      class="project-search__keyword"
      placeholder="按项目名称或编号搜索"
      clearable
      :prefix-icon="Search"
      @input="handleInput"
      @clear="handleClear"
    />

    <el-select
      class="project-search__status"
      placeholder="全部状态"
      clearable
      :model-value="status"
      @change="handleStatus"
    >
      <el-option
        v-for="option in PROJECT_STATUS_OPTIONS"
        :key="option.value"
        :label="option.label"
        :value="option.value"
      />
    </el-select>

    <el-button :loading="loading" @click="emit('refresh')">
      <el-icon><Refresh /></el-icon>
      <span>刷新</span>
    </el-button>
  </div>
</template>

<style scoped>
.project-search {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 12px;
}

.project-search__keyword {
  width: 280px;
}

.project-search__status {
  width: 160px;
}
</style>
