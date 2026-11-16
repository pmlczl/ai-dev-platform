<script setup lang="ts">
/**
 * The table of the files of a task.
 *
 * It is used for the requirement documents of a task and for the results of
 * its workflow runs. The content of a file is never linked directly: the row
 * asks the page to download it, and the page fetches it through the backend.
 */
import StatusTag from '@/components/common/StatusTag.vue'
import { artifactStageLabel, fileTypeLabel } from '@/constants/artifact'
import { artifactDisplayName } from '@/utils/download'
import { formatDateTime, formatFileSize } from '@/utils/format'

import type { ArtifactRead } from '@/types'

withDefaults(
  defineProps<{
    artifacts: ArtifactRead[]
    /** Show the stage of every file. */
    showStage?: boolean
    /** Show where the file came from - a workflow run or an upload. */
    showSource?: boolean
    /** The label of the time column. */
    timeLabel?: string
    /** The ids of the files that are being downloaded. */
    downloading?: Set<string>
  }>(),
  {
    showStage: false,
    showSource: false,
    timeLabel: '创建时间',
    downloading: () => new Set<string>(),
  },
)

const emit = defineEmits<{
  (event: 'download', artifact: ArtifactRead): void
}>()

function splitDateTime(value: string): { date: string; time: string } {
  const [date, time = ''] = formatDateTime(value).split(' ')
  return { date, time }
}
</script>

<template>
  <el-table class="artifact-table" :data="artifacts" row-key="id" stripe style="width: 100%">
    <el-table-column label="文件名" min-width="220">
      <template #default="{ row }: { row: ArtifactRead }">
        <el-tooltip :content="row.relative_path" placement="top">
          <span class="artifact-table__name">{{ artifactDisplayName(row) }}</span>
        </el-tooltip>
      </template>
    </el-table-column>

    <el-table-column label="类型" width="96" show-overflow-tooltip>
      <template #default="{ row }: { row: ArtifactRead }">
        {{ fileTypeLabel(row.file_type) }}
      </template>
    </el-table-column>

    <el-table-column v-if="showStage" label="阶段" width="72" align="center">
      <template #default="{ row }: { row: ArtifactRead }">
        {{ artifactStageLabel(row.stage) }}
      </template>
    </el-table-column>

    <el-table-column label="版本" width="64" align="center">
      <template #default="{ row }: { row: ArtifactRead }">v{{ row.version }}</template>
    </el-table-column>

    <el-table-column label="大小" width="90" align="right">
      <template #default="{ row }: { row: ArtifactRead }">
        {{ formatFileSize(row.size_bytes) }}
      </template>
    </el-table-column>

    <el-table-column v-if="showSource" label="来源" width="96" align="center">
      <template #default="{ row }: { row: ArtifactRead }">
        <el-tag v-if="row.workflow_instance_id" type="warning" size="small" effect="plain">
          模拟成果
        </el-tag>
        <el-tag v-else type="info" size="small" effect="plain">人工上传</el-tag>
      </template>
    </el-table-column>

    <el-table-column label="审核状态" width="92" align="center">
      <template #default="{ row }: { row: ArtifactRead }">
        <StatusTag :status="row.review_status" kind="artifact" />
      </template>
    </el-table-column>

    <el-table-column :label="timeLabel" width="110">
      <template #default="{ row }: { row: ArtifactRead }">
        <div class="artifact-table__time">
          <span>{{ splitDateTime(row.created_at).date }}</span>
          <span class="artifact-table__time-part">{{ splitDateTime(row.created_at).time }}</span>
        </div>
      </template>
    </el-table-column>

    <el-table-column label="操作" width="72" fixed="right" align="center">
      <template #default="{ row }: { row: ArtifactRead }">
        <el-button
          link
          type="primary"
          size="small"
          :loading="downloading.has(row.id)"
          @click="emit('download', row)"
        >
          下载
        </el-button>
      </template>
    </el-table-column>
  </el-table>
</template>

<style scoped>
.artifact-table__name {
  display: inline-block;
  max-width: 100%;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  vertical-align: bottom;
}

.artifact-table__time {
  display: flex;
  flex-direction: column;
  line-height: 1.4;
}

.artifact-table__time-part {
  color: var(--el-text-color-secondary);
  font-size: 12px;
}
</style>
