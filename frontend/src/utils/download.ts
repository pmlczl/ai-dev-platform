/**
 * Saving a file the backend sent.
 *
 * The content of a file is always fetched through the download endpoint of
 * the backend (`GET /artifacts/{id}/download`). The browser never builds a
 * path to the storage: the blob the backend answered is handed to the user
 * through a temporary object URL.
 */
import { downloadArtifact } from '@/api/artifacts'

import type { RequestOptions } from '@/api/client'
import type { ArtifactRead } from '@/types'

/** Hand a blob to the browser as a download. */
export function saveBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = filename
  anchor.style.display = 'none'
  document.body.appendChild(anchor)
  anchor.click()
  document.body.removeChild(anchor)
  // The URL is revoked only after the browser had ample time to finish the
  // download; revoking it while the download is still in progress cancels it.
  window.setTimeout(() => URL.revokeObjectURL(url), 60_000)
}

/** The name a downloaded file is saved under. */
export function artifactDisplayName(artifact: ArtifactRead): string {
  if (artifact.original_filename) {
    return artifact.original_filename
  }
  const segments = artifact.relative_path.split('/')
  return segments[segments.length - 1] || artifact.id
}

/**
 * Download a file of the backend and save it.
 *
 * The name of the file comes from the `Content-Disposition` header of the
 * backend; the metadata of the file is the fallback.
 */
export async function saveArtifact(
  artifact: ArtifactRead,
  options: RequestOptions = {},
): Promise<void> {
  const result = await downloadArtifact(artifact.id, options)
  saveBlob(result.blob, result.filename ?? artifactDisplayName(artifact))
}
