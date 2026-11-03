import { http } from './client'

/** Payload of `GET /api/v1/health`. */
export interface HealthInfo {
  status: string
  app: string
  version: string
  environment: string
  timestamp: string
}

/** Payload of `GET /api/v1/health/ready`. */
export interface ReadinessInfo {
  status: string
  database: {
    status: string
    latency_ms: number | null
  }
  timestamp: string
}

/** Fetch the liveness information of the backend. */
export async function fetchHealth(): Promise<HealthInfo> {
  const { data } = await http.get<HealthInfo>('/health')
  return data
}

/** Fetch the readiness information of the backend (includes the database probe). */
export async function fetchReadiness(): Promise<ReadinessInfo> {
  const { data } = await http.get<ReadinessInfo>('/health/ready')
  return data
}
