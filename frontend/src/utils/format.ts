/**
 * Formatting helpers.
 *
 * The backend sends timestamps as ISO strings and sizes as plain numbers.
 * The presentation of both is decided here, so every page shows them the
 * same way.
 */

/** The text that is shown when there is no value. */
export const EMPTY_TEXT = '—'

/**
 * Format an ISO timestamp as `YYYY-MM-DD HH:mm:ss`.
 *
 * The backend sends a timezone aware ISO string; it is converted into the
 * local time of the browser.
 */
export function formatDateTime(value?: string | null, fallback = EMPTY_TEXT): string {
  if (!value) {
    return fallback
  }
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) {
    return value
  }
  const pad = (part: number): string => String(part).padStart(2, '0')
  return (
    `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ` +
    `${pad(date.getHours())}:${pad(date.getMinutes())}:${pad(date.getSeconds())}`
  )
}

/** Format an ISO timestamp as `YYYY-MM-DD`. */
export function formatDate(value?: string | null, fallback = EMPTY_TEXT): string {
  if (!value) {
    return fallback
  }
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) {
    return value
  }
  const pad = (part: number): string => String(part).padStart(2, '0')
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`
}

/**
 * Format a number of bytes.
 *
 * The unit is chosen so that the result stays short: a file of a workflow
 * run is measured in kilobytes, an upload in megabytes.
 */
export function formatFileSize(bytes?: number | null, fallback = EMPTY_TEXT): string {
  if (bytes === null || bytes === undefined) {
    return fallback
  }
  if (!Number.isFinite(bytes) || bytes < 0) {
    return fallback
  }
  if (bytes < 1024) {
    return `${bytes} B`
  }
  const units = ['KB', 'MB', 'GB', 'TB']
  let value = bytes / 1024
  let unit = 0
  while (value >= 1024 && unit < units.length - 1) {
    value /= 1024
    unit += 1
  }
  return `${value.toFixed(value >= 100 ? 0 : 1)} ${units[unit]}`
}

/**
 * Shorten a path so that it fits into a table cell.
 *
 * The first segment and the last two are kept, the rest is replaced by an
 * ellipsis. The name of the file always stays visible.
 */
export function formatPath(path?: string | null, maxLength = 48, fallback = EMPTY_TEXT): string {
  if (!path) {
    return fallback
  }
  if (path.length <= maxLength) {
    return path
  }
  const segments = path.split('/')
  if (segments.length <= 3) {
    return `${path.slice(0, maxLength - 1)}…`
  }
  const head = segments[0]
  const tail = segments.slice(-2).join('/')
  const result = `${head}/…/${tail}`
  return result.length <= maxLength ? result : `${result.slice(0, maxLength - 1)}…`
}

/** The name of a file without its directory. */
export function formatFileName(path?: string | null, fallback = EMPTY_TEXT): string {
  if (!path) {
    return fallback
  }
  const segments = path.split('/')
  return segments[segments.length - 1] || fallback
}

/**
 * Describe how long ago a timestamp was written.
 *
 * The text is meant for a table cell: it stays short and it is relative, so
 * a reader sees at a glance how old an entry is.
 */
export function formatRelativeTime(value?: string | null, fallback = EMPTY_TEXT): string {
  if (!value) {
    return fallback
  }
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) {
    return value
  }
  const seconds = Math.floor((Date.now() - date.getTime()) / 1000)
  if (seconds < 0) {
    return formatDateTime(value)
  }
  if (seconds < 60) {
    return '刚刚'
  }
  const minutes = Math.floor(seconds / 60)
  if (minutes < 60) {
    return `${minutes} 分钟前`
  }
  const hours = Math.floor(minutes / 60)
  if (hours < 24) {
    return `${hours} 小时前`
  }
  const days = Math.floor(hours / 24)
  if (days < 30) {
    return `${days} 天前`
  }
  return formatDate(value)
}
