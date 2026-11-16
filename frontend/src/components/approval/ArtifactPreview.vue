<script setup lang="ts">
/**
 * The in-page preview of a file the backend stores.
 *
 * The content is fetched through the download endpoint of the backend - the
 * browser never assembles a path to the storage. What the answer is worth
 * depends on the type of the file:
 *
 * * Markdown and plain text (JSON and YAML included) are read as text and
 *   turned into HTML by `@/utils/markdown`, which escapes the content before
 *   it adds any tag of its own;
 * * a PDF is handed to the viewer of the browser through a temporary object
 *   URL;
 * * every other type is only offered for download, because the platform has
 *   no renderer for it.
 */
import { computed, onBeforeUnmount, ref, watch } from 'vue'

import PageState from '@/components/common/PageState.vue'
import { downloadArtifact } from '@/api/artifacts'
import { describeApiError } from '@/api/client'
import {
  fileTypeLabel,
  isMarkdownFileType,
  isPdfFileType,
  isTextFileType,
} from '@/constants/artifact'
import { saveBlob } from '@/utils/download'
import { renderMarkdown, renderPlainText } from '@/utils/markdown'

import type { ArtifactRead } from '@/types'

const props = withDefaults(
  defineProps<{
    /** The file to show. Without it the component is empty. */
    artifact?: ArtifactRead | null
    /** The metadata of the file is still loading. */
    metadataLoading?: boolean
    emptyText?: string
    /** Show the name and the size above the content. */
    showHeader?: boolean
  }>(),
  { artifact: null, metadataLoading: false, emptyText: '没有可预览的文件', showHeader: true },
)

const content = ref<string | null>(null)
const objectUrl = ref<string | null>(null)
const loading = ref(false)
const downloading = ref(false)
const error = ref<string | null>(null)

/** What the component can do with the file. */
const mode = computed<'markdown' | 'text' | 'pdf' | 'other' | 'none'>(() => {
  const type = props.artifact?.file_type
  if (!props.artifact || !type) {
    return 'none'
  }
  if (isMarkdownFileType(type)) {
    return 'markdown'
  }
  if (isTextFileType(type)) {
    return 'text'
  }
  if (isPdfFileType(type)) {
    return 'pdf'
  }
  return 'other'
})

const html = computed<string | null>(() => {
  if (content.value === null) {
    return null
  }
  return mode.value === 'markdown'
    ? renderMarkdown(content.value)
    : renderPlainText(content.value)
})

function releaseObjectUrl(): void {
  if (objectUrl.value) {
    URL.revokeObjectURL(objectUrl.value)
    objectUrl.value = null
  }
}

/** Read the file again from the backend. */
async function load(): Promise<void> {
  releaseObjectUrl()
  content.value = null
  const artifact = props.artifact
  if (!artifact) {
    return
  }
  loading.value = true
  error.value = null
  try {
    const result = await downloadArtifact(artifact.id, { silent: true })
    if (mode.value === 'pdf') {
      objectUrl.value = URL.createObjectURL(result.blob)
    } else if (mode.value === 'markdown' || mode.value === 'text') {
      content.value = await result.blob.text()
    } else {
      // Nothing to render; the file stays available through the button.
      content.value = null
    }
  } catch (caught) {
    error.value = describeApiError(caught)
  } finally {
    loading.value = false
  }
}

/** Save the file the way the approval page offers it. */
async function handleDownload(): Promise<void> {
  const artifact = props.artifact
  if (!artifact) {
    return
  }
  downloading.value = true
  try {
    const result = await downloadArtifact(artifact.id, { silent: true })
    saveBlob(result.blob, result.filename ?? artifact.original_filename ?? 'artifact')
  } catch (caught) {
    error.value = describeApiError(caught)
  } finally {
    downloading.value = false
  }
}

watch(
  () => props.artifact?.id,
  () => {
    void load()
  },
  { immediate: true },
)

onBeforeUnmount(releaseObjectUrl)

defineExpose({ reload: load })
</script>

<template>
  <div class="artifact-preview">
    <div v-if="showHeader && artifact" class="artifact-preview__bar">
      <div class="artifact-preview__name" :title="artifact.relative_path">
        {{ artifact.original_filename || artifact.relative_path }}
        <el-tag size="small" effect="plain">{{ fileTypeLabel(artifact.file_type) }}</el-tag>
        <el-tag size="small" effect="plain">v{{ artifact.version }}</el-tag>
      </div>
      <div class="artifact-preview__actions">
        <el-button size="small" text @click="load">
          <el-icon><Refresh /></el-icon>
          <span>重新加载</span>
        </el-button>
        <el-button size="small" type="primary" plain :loading="downloading" @click="handleDownload">
          <el-icon><Download /></el-icon>
          <span>下载原文件</span>
        </el-button>
      </div>
    </div>

    <PageState
      :loading="metadataLoading || loading"
      :error="error"
      :empty="!artifact"
      :empty-text="emptyText"
      loading-text="正在读取文件内容…"
      min-height="220px"
    >
      <template #error>
        <el-button type="primary" plain @click="load">重试</el-button>
      </template>

      <div v-if="mode === 'markdown' || mode === 'text'" class="artifact-preview__body">
        <!-- The HTML is produced by `@/utils/markdown`: the content of the
             file is escaped before a single tag is added, so nothing of it
             is ever interpreted as markup. -->
        <div class="artifact-preview__document" v-html="html" />
      </div>

      <div v-else-if="mode === 'pdf'" class="artifact-preview__body">
        <iframe
          v-if="objectUrl"
          class="artifact-preview__pdf"
          :src="objectUrl"
          title="PDF 预览"
        />
        <p v-else class="artifact-preview__hint">PDF 正在加载…</p>
        <p class="artifact-preview__note">
          PDF 由浏览器内置查看器渲染；无法显示时请使用「下载原文件」。
        </p>
      </div>

      <div v-else-if="mode === 'other'" class="artifact-preview__body">
        <el-alert
          type="info"
          :closable="false"
          show-icon
          title="该类型没有页内预览，只能下载后查看。"
        />
      </div>

      <div v-else class="artifact-preview__body">
        <p class="artifact-preview__hint">没有可预览的文件内容。</p>
      </div>
    </PageState>
  </div>
</template>

<style scoped>
.artifact-preview {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.artifact-preview__bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  flex-wrap: wrap;
}

.artifact-preview__name {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-weight: 500;
}

.artifact-preview__actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

.artifact-preview__body {
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 6px;
  background-color: var(--el-fill-color-extra-light);
}

.artifact-preview__document {
  padding: 16px 20px;
  max-height: 520px;
  overflow: auto;
  font-size: 14px;
  line-height: 1.7;
  color: var(--el-text-color-primary);
}

.artifact-preview__document :deep(h1),
.artifact-preview__document :deep(h2),
.artifact-preview__document :deep(h3) {
  margin: 16px 0 8px;
  font-weight: 600;
}

.artifact-preview__document :deep(h1) {
  font-size: 20px;
}

.artifact-preview__document :deep(h2) {
  font-size: 17px;
}

.artifact-preview__document :deep(h3) {
  font-size: 15px;
}

.artifact-preview__document :deep(p) {
  margin: 8px 0;
}

.artifact-preview__document :deep(ul),
.artifact-preview__document :deep(ol) {
  margin: 8px 0 8px 22px;
  padding: 0;
}

.artifact-preview__document :deep(code) {
  padding: 1px 5px;
  border-radius: 4px;
  background-color: var(--el-fill-color);
  font-family: var(--el-font-family-monospace, monospace);
  font-size: 13px;
}

.artifact-preview__document :deep(pre) {
  margin: 10px 0;
  padding: 12px;
  border-radius: 6px;
  background-color: var(--el-fill-color);
  overflow: auto;
}

.artifact-preview__document :deep(pre code) {
  padding: 0;
  background: none;
}

.artifact-preview__document :deep(.md-plain) {
  margin: 0;
  background: none;
  white-space: pre-wrap;
  word-break: break-word;
}

.artifact-preview__document :deep(blockquote) {
  margin: 8px 0;
  padding-left: 12px;
  border-left: 3px solid var(--el-border-color);
  color: var(--el-text-color-secondary);
}

.artifact-preview__document :deep(a) {
  color: var(--el-color-primary);
  text-decoration: none;
}

.artifact-preview__pdf {
  display: block;
  width: 100%;
  height: 520px;
  border: none;
  background-color: var(--el-bg-color);
}

.artifact-preview__note {
  margin: 0;
  padding: 8px 12px;
  color: var(--el-text-color-secondary);
  font-size: 12px;
}

.artifact-preview__hint {
  margin: 0;
  padding: 16px;
  color: var(--el-text-color-secondary);
  text-align: center;
}
</style>
