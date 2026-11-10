import axios from 'axios'
import type { AxiosError, AxiosInstance } from 'axios'
import { ElMessage } from 'element-plus'

import type { ApiErrorPayload } from '@/types'

/** Shape of the unified error envelope returned by the backend. */
export type { ApiErrorPayload }

/**
 * Base URL of the backend API.
 *
 * In development the Vite dev server proxies `/api` to the FastAPI backend
 * (see `vite.config.ts`); in the Docker setup nginx does the same. When the
 * frontend is deployed on a different origin, set `VITE_API_BASE_URL`.
 */
export const API_BASE_URL: string = import.meta.env.VITE_API_BASE_URL ?? '/api/v1'

/**
 * The single HTTP client of the application.
 *
 * The default `Content-Type` is deliberately not set: axios derives it from
 * the payload - a JSON body gets `application/json`, a `FormData` body gets
 * `multipart/form-data` together with the boundary it generates itself.
 * Setting it here would break every file upload.
 */
export const http: AxiosInstance = axios.create({
  baseURL: API_BASE_URL,
  timeout: 15000,
})

declare module 'axios' {
  export interface AxiosRequestConfig {
    /**
     * Suppress the automatic error notification of the client.
     *
     * A page that handles an error on its own - for example to keep a form
     * filled in - sets this flag.
     */
    silent?: boolean
  }
}

/**
 * The hint that is put in front of the message of the backend.
 *
 * The backend already sends a readable message; the hint tells the user what
 * kind of problem it is.
 */
const ERROR_HINTS: Record<string, string> = {
  NOT_FOUND: '未找到',
  CONFLICT: '状态冲突',
  VALIDATION_ERROR: '参数错误',
  SERVICE_UNAVAILABLE: '服务不可用',
  UNAUTHORIZED: '未授权',
  FORBIDDEN: '没有权限',
  PAYLOAD_TOO_LARGE: '文件过大',
  METHOD_NOT_ALLOWED: '方法不允许',
  INTERNAL_SERVER_ERROR: '服务内部错误',
  APP_ERROR: '请求失败',
}

/**
 * Request interceptor.
 *
 * The platform has no login yet, so there is no token to attach. The hook is
 * the place where the header is added once the identity exists - every
 * request passes through it.
 */
http.interceptors.request.use(
  (config) => config,
  (error: Error) => Promise.reject(error),
)

/** Read a header of an axios response without fighting its union type. */
function readHeader(headers: unknown, name: string): string | null {
  if (!headers || typeof headers !== 'object') {
    return null
  }
  const value = (headers as Record<string, unknown>)[name]
  return typeof value === 'string' ? value : null
}

/**
 * Build the text that is shown to the user.
 *
 * The text always carries the `request_id` of the backend: it is the only
 * thing that connects a message on the screen with the log of the service.
 */
export function describeApiError(error: unknown): string {
  if (!axios.isAxiosError<ApiErrorPayload>(error)) {
    return extractErrorMessage(error)
  }

  const payload = error.response?.data
  const code = payload?.code ?? 'APP_ERROR'
  const hint = ERROR_HINTS[code] ?? ERROR_HINTS.APP_ERROR
  const message = payload?.message ?? error.message ?? '请求失败'
  const requestId =
    payload?.request_id ?? readHeader(error.response?.headers, 'x-request-id')

  const head = code === 'APP_ERROR' && !payload ? message : `${hint}：${message}`
  return requestId ? `${head}（request_id: ${requestId}）` : head
}

/**
 * Response interceptor.
 *
 * Every failure of the API ends here: the error is enriched with the code
 * and the correlation id of the request and - unless the caller asked for
 * silence - the user is told what happened.
 */
http.interceptors.response.use(
  (response) => response,
  (error: AxiosError<ApiErrorPayload>) => {
    const payload = error.response?.data
    const code = payload?.code ?? 'APP_ERROR'
    const requestId =
      payload?.request_id ?? readHeader(error.response?.headers, 'x-request-id')
    const message = payload?.message ?? error.message ?? '请求失败'

    const enriched = Object.assign(error, {
      message,
      code,
      requestId,
      status: error.response?.status ?? 0,
      payload,
    })

    if (!error.config?.silent) {
      ElMessage.error(describeApiError(error))
    }
    return Promise.reject(enriched)
  },
)

/** Extract a human readable message from an unknown error value. */
export function extractErrorMessage(error: unknown): string {
  if (axios.isAxiosError<ApiErrorPayload>(error)) {
    return error.response?.data?.message ?? error.message
  }
  if (error instanceof Error) {
    return error.message
  }
  return 'Unknown error'
}

/** Read the correlation id of a failed request, if the backend sent one. */
export function extractRequestId(error: unknown): string | null {
  if (!axios.isAxiosError<ApiErrorPayload>(error)) {
    return null
  }
  return (
    error.response?.data?.request_id ??
    readHeader(error.response?.headers, 'x-request-id')
  )
}
