/**
 * The presentation of the files of the backend.
 *
 * The limits mirror the ones of `backend/app/services/artifact_types.py`
 * and the `ARTIFACT_MAX_SIZE_BYTES` setting: the browser refuses a file the
 * backend would refuse anyway, so the user is told before the upload starts.
 * The backend stays the authority - a file that passes here is still checked
 * on the server.
 */
import type { ArtifactStage } from '@/types'

/** The extensions the backend accepts - `EXTENSION_MIME_TYPES` of the backend. */
export const ARTIFACT_ALLOWED_EXTENSIONS = [
  'pdf',
  'docx',
  'md',
  'markdown',
  'txt',
  'json',
  'yaml',
  'yml',
] as const

/** The largest file the backend accepts - 50 MiB, the default of the setting. */
export const ARTIFACT_MAX_SIZE_BYTES = 50 * 1024 * 1024

/** The `accept` attribute of the file picker. */
export const ARTIFACT_ACCEPT = ARTIFACT_ALLOWED_EXTENSIONS.map((ext) => `.${ext}`).join(',')

/** The extension of a file name, lower case, without the dot. */
export function fileExtension(name: string): string {
  const index = name.lastIndexOf('.')
  if (index < 0 || index === name.length - 1) {
    return ''
  }
  return name.slice(index + 1).toLowerCase()
}

/** True when the backend accepts the extension of the file. */
export function isAllowedArtifactExtension(name: string): boolean {
  return (ARTIFACT_ALLOWED_EXTENSIONS as readonly string[]).includes(fileExtension(name))
}

/** The labels of the stages. */
export const ARTIFACT_STAGE_LABELS: Record<ArtifactStage, string> = {
  design: '设计',
  development: '开发',
  testing: '测试',
  delivery: '交付',
  other: '其他',
}

/** The stages in the order of the backend enumeration. */
export const ARTIFACT_STAGE_VALUES: ArtifactStage[] = [
  'design',
  'development',
  'testing',
  'delivery',
  'other',
]

/** The options of a select field that filters by stage. */
export const ARTIFACT_STAGE_OPTIONS = ARTIFACT_STAGE_VALUES.map((value) => ({
  value,
  label: ARTIFACT_STAGE_LABELS[value],
}))

/** The label of a stage - the raw value is returned when it is unknown. */
export function artifactStageLabel(stage: string): string {
  return ARTIFACT_STAGE_LABELS[stage as ArtifactStage] ?? stage
}

/**
 * A short label of the MIME type the backend stores in `file_type`.
 *
 * The values are the ones of `EXTENSION_MIME_TYPES` of the backend; an
 * unknown type is shown as it is.
 */
const FILE_TYPE_LABELS: Record<string, string> = {
  'application/pdf': 'PDF',
  'application/vnd.openxmlformats-officedocument.wordprocessingml.document': 'Word',
  'text/markdown': 'Markdown',
  'text/plain': '文本',
  'application/json': 'JSON',
  'application/yaml': 'YAML',
  'application/x-yaml': 'YAML',
  'text/yaml': 'YAML',
}

/** The label of a file type. */
export function fileTypeLabel(fileType: string | null | undefined): string {
  if (!fileType) {
    return '—'
  }
  return FILE_TYPE_LABELS[fileType] ?? fileType
}

/** True when the file is text that can be shown in the page. */
export function isTextFileType(fileType: string | null | undefined): boolean {
  if (!fileType) {
    return false
  }
  return (
    fileType === 'text/markdown' ||
    fileType === 'text/plain' ||
    fileType === 'application/json' ||
    fileType === 'application/yaml' ||
    fileType === 'application/x-yaml' ||
    fileType === 'text/yaml'
  )
}

/** True when the file is Markdown. */
export function isMarkdownFileType(fileType: string | null | undefined): boolean {
  return fileType === 'text/markdown'
}

/** True when the file is a PDF. */
export function isPdfFileType(fileType: string | null | undefined): boolean {
  return fileType === 'application/pdf'
}
