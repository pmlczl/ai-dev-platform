import axios from 'axios'
import type { AxiosError, AxiosInstance } from 'axios'

/** Shape of the unified error envelope returned by the backend. */
export interface ApiErrorPayload {
  code: string
  message: string
  detail?: unknown
  request_id?: string
  timestamp?: string
}

/**
 * Base URL of the backend API.
 *
 * In development the Vite dev server proxies `/api` to the FastAPI backend
 * (see `vite.config.ts`); in the Docker setup nginx does the same. When the
 * frontend is deployed on a different origin, set `VITE_API_BASE_URL`.
 */
export const API_BASE_URL: string = import.meta.env.VITE_API_BASE_URL ?? '/api/v1'

export const http: AxiosInstance = axios.create({
  baseURL: API_BASE_URL,
  timeout: 15000,
  headers: {
    'Content-Type': 'application/json',
  },
})

http.interceptors.response.use(
  (response) => response,
  (error: AxiosError<ApiErrorPayload>) => {
    const payload = error.response?.data
    const message =
      payload?.message ?? error.message ?? 'Request failed'
    return Promise.reject(Object.assign(error, { message }))
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
