import { http } from './client'

import type {
  ArtifactRead,
  ArtifactReviewRequest,
  ArtifactReviewStatus,
  ArtifactStage,
  Page,
} from '@/types'

/** Filters of the artifact list of a task. */
export interface ArtifactListParams {
  page?: number
  page_size?: number
  review_status?: ArtifactReviewStatus
  stage?: ArtifactStage
  keyword?: string
}

/** The payload of an upload. */
export interface ArtifactUploadPayload {
  file: File
  relative_path?: string
  stage?: ArtifactStage
  created_by?: string
}

/** The content of a download. */
export interface ArtifactDownload {
  blob: Blob
  /** The digest the backend computed, taken from the `X-Content-SHA256` header. */
  sha256: string | null
  filename: string | null
}

/**
 * Read the file name of a `Content-Disposition` header.
 *
 * The backend sends the RFC 5987 form (`filename*=UTF-8''...`) for a name
 * that is not plain ASCII and the plain form otherwise.
 */
function parseFilename(header: string | null): string | null {
  if (!header) {
    return null
  }
  const encoded = /filename\*=(?:UTF-8'')?([^;]+)/i.exec(header)
  if (encoded) {
    try {
      return decodeURIComponent(encoded[1].trim())
    } catch {
      return encoded[1].trim()
    }
  }
  const plain = /filename="([^"]*)"/i.exec(header)
  if (plain) {
    return plain[1]
  }
  return null
}

/**
 * Build the body of an upload.
 *
 * The `FormData` is handed to axios as it is: the browser sets the
 * `Content-Type` together with the boundary it generates, so the header must
 * not be written by hand.
 */
function buildUploadForm(payload: ArtifactUploadPayload): FormData {
  const form = new FormData()
  form.append('file', payload.file)
  if (payload.relative_path) {
    form.append('relative_path', payload.relative_path)
  }
  if (payload.stage) {
    form.append('stage', payload.stage)
  }
  if (payload.created_by) {
    form.append('created_by', payload.created_by)
  }
  return form
}

/** Fetch one page of the files of a task. */
export async function fetchTaskArtifacts(
  taskId: string,
  params: ArtifactListParams = {},
): Promise<Page<ArtifactRead>> {
  const { data } = await http.get<Page<ArtifactRead>>(`/tasks/${taskId}/artifacts`, {
    params,
  })
  return data
}

/** Fetch the metadata of one file. */
export async function fetchArtifact(artifactId: string): Promise<ArtifactRead> {
  const { data } = await http.get<ArtifactRead>(`/artifacts/${artifactId}`)
  return data
}

/** Upload a file into a task. */
export async function uploadArtifact(
  taskId: string,
  payload: ArtifactUploadPayload,
): Promise<ArtifactRead> {
  const { data } = await http.post<ArtifactRead>(
    `/tasks/${taskId}/artifacts`,
    buildUploadForm(payload),
  )
  return data
}

/** Create a new version of a file - the old one becomes superseded. */
export async function createArtifactRevision(
  artifactId: string,
  payload: { file: File; stage?: ArtifactStage; created_by?: string },
): Promise<ArtifactRead> {
  const form = new FormData()
  form.append('file', payload.file)
  if (payload.stage) {
    form.append('stage', payload.stage)
  }
  if (payload.created_by) {
    form.append('created_by', payload.created_by)
  }
  const { data } = await http.post<ArtifactRead>(
    `/artifacts/${artifactId}/revisions`,
    form,
  )
  return data
}

/** Download the content of a file. */
export async function downloadArtifact(
  artifactId: string,
): Promise<ArtifactDownload> {
  const response = await http.get(`/artifacts/${artifactId}/download`, {
    responseType: 'blob',
  })
  const headers = response.headers as unknown as Record<string, string>
  return {
    blob: response.data as Blob,
    sha256: headers['x-content-sha256'] ?? null,
    filename: parseFilename(headers['content-disposition'] ?? null),
  }
}

/**
 * Move a file into a reviewed state.
 *
 * This is the review of a file - it is not the approval of a workflow run.
 * The two are separate flows and the user interface keeps them apart.
 */
export async function reviewArtifact(
  artifactId: string,
  payload: ArtifactReviewRequest,
): Promise<ArtifactRead> {
  const { data } = await http.post<ArtifactRead>(
    `/artifacts/${artifactId}/review`,
    payload,
  )
  return data
}
