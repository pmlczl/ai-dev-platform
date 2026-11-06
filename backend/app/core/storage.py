"""Generic file storage primitives.

The module deliberately knows nothing about the domain: it provides safe path
handling, exclusive writes and digest computation on top of a configurable root
directory. Policy decisions - which file types are accepted, how a file is
named in the database - belong to the service layer.

Two rules are enforced here because breaking them would be a security issue:

* a stored file name is always a single path segment and never contains
  traversal or control characters,
* a file is always created exclusively, so an existing revision can never be
  overwritten.
"""

from __future__ import annotations

import hashlib
import os
import re
import shutil
import unicodedata
from collections.abc import AsyncIterable
from pathlib import Path, PurePosixPath

import anyio

from app.core.config import get_settings
from app.core.exceptions import ConflictException, PayloadTooLargeException, ValidationException

#: Characters that are never allowed inside a stored path segment.
_FORBIDDEN_CHARS = re.compile(r'[\x00-\x1f<>:"/\\|?*]')
#: Windows device names that must not be used as a file name.
_RESERVED_NAMES = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    *(f"COM{index}" for index in range(1, 10)),
    *(f"LPT{index}" for index in range(1, 10)),
}
#: Longest file name (without extension) that is written to disk.
MAX_FILENAME_LENGTH = 120
#: Longest logical relative path that is accepted.
MAX_RELATIVE_PATH_LENGTH = 500
#: Size of the blocks used for hashing and copying.
BLOCK_SIZE = 1024 * 1024
#: Name of the directory that holds in-flight uploads.
TEMP_DIR_NAME = ".tmp"


def storage_root() -> Path:
    """Return the root directory of the file storage and make sure it exists."""

    root = get_settings().storage_root_path
    root.mkdir(parents=True, exist_ok=True)
    return root


def temp_dir() -> Path:
    """Return the directory that holds in-flight uploads."""

    path = storage_root() / TEMP_DIR_NAME
    path.mkdir(parents=True, exist_ok=True)
    return path


def sanitize_filename(filename: str) -> str:
    """Reduce an uploaded file name to a single safe path segment.

    A name that carries a path - an absolute path, a Windows path or a name
    that is a traversal segment - is rejected instead of being repaired: no
    legitimate upload needs it, and silently dropping the prefix would hide
    an attempt to escape the storage directory.
    """

    if not filename or not filename.strip():
        raise ValidationException("文件名不能为空")

    candidate = unicodedata.normalize("NFC", filename).strip()
    if "/" in candidate or "\\" in candidate:
        raise ValidationException("文件名不能包含路径分隔符")
    if candidate in {".", ".."}:
        raise ValidationException("文件名不合法")

    cleaned = _FORBIDDEN_CHARS.sub("_", candidate).strip()
    # Leading dots would create hidden files and are not needed.
    cleaned = cleaned.lstrip(".").strip()
    if not cleaned:
        raise ValidationException("文件名不合法")

    stem, dot, extension = cleaned.rpartition(".")
    if not dot:
        stem, extension = cleaned, ""
    stem = stem.strip() or "file"
    stem = stem[:MAX_FILENAME_LENGTH]
    if stem.upper() in _RESERVED_NAMES or extension.upper() in _RESERVED_NAMES:
        raise ValidationException("文件名不合法")
    return f"{stem}.{extension.lower()}" if extension else stem


def sanitize_segment(segment: str) -> str:
    """Reduce one path segment of a logical path to a safe name."""

    cleaned = _FORBIDDEN_CHARS.sub("_", segment).strip().lstrip(".").strip()
    if not cleaned:
        raise ValidationException("路径片段不合法")
    return cleaned[:MAX_FILENAME_LENGTH]


def normalize_relative_path(raw: str) -> str:
    """Normalise a logical path and reject every attempt at path traversal.

    The result is always a relative POSIX path without ``.`` or ``..``
    segments and never starts at the filesystem root.
    """

    if not raw or not raw.strip():
        raise ValidationException("相对路径不能为空")

    candidate = raw.strip().replace("\\", "/")
    if candidate.startswith("/") or re.match(r"^[A-Za-z]:", candidate):
        raise ValidationException("相对路径必须是项目内的相对路径")

    segments: list[str] = []
    for segment in candidate.split("/"):
        if segment in {"", "."}:
            continue
        if segment == "..":
            raise ValidationException("相对路径不能包含上级目录引用")
        segments.append(sanitize_segment(segment))

    if not segments:
        raise ValidationException("相对路径不能为空")
    normalized = "/".join(segments)
    if len(normalized) > MAX_RELATIVE_PATH_LENGTH:
        raise ValidationException("相对路径过长")
    return normalized


def build_storage_path(
    *,
    project_id: str,
    task_id: str | None,
    relative_path: str,
    version: int,
) -> str:
    """Build the storage relative path of one file revision.

    The version is part of the path, so two revisions of the same logical file
    never share a directory and therefore can never overwrite each other.
    """

    parts = ["projects", project_id]
    if task_id:
        parts.extend(["tasks", task_id])
    parts.append(f"v{version}")
    parts.extend(PurePosixPath(relative_path).parts)
    return "/".join(parts)


def resolve_within_root(relative_path: str) -> Path:
    """Resolve a storage relative path and make sure it stays inside the root.

    The check is the last line of defence against path traversal: even if a
    stored path were manipulated, the resolved file could never leave the
    storage directory.
    """

    root = storage_root()
    candidate = (root / relative_path).resolve()
    if candidate != root and root not in candidate.parents:
        raise ValidationException("文件路径不合法")
    return candidate


async def write_stream_exclusive(
    destination: Path,
    chunks: AsyncIterable[bytes],
    max_bytes: int,
) -> tuple[int, str]:
    """Write a byte stream into a new file and return its size and digest.

    The file is created exclusively: if it already exists the call fails with
    a conflict instead of overwriting the existing content. The size limit is
    enforced while the stream is consumed, so an oversized upload is stopped
    instead of being buffered completely.
    """

    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        handle = await anyio.to_thread.run_sync(destination.open, "xb")
    except FileExistsError as exc:
        raise ConflictException("目标文件已存在，拒绝覆盖") from exc

    digest = hashlib.sha256()
    size = 0
    try:
        async for chunk in chunks:
            size += len(chunk)
            if size > max_bytes:
                raise PayloadTooLargeException(
                    f"文件超过大小上限（{max_bytes} 字节）",
                )
            digest.update(chunk)
            await anyio.to_thread.run_sync(handle.write, chunk)
    except BaseException:
        await anyio.to_thread.run_sync(handle.close)
        await anyio.to_thread.run_sync(destination.unlink, True)
        raise
    await anyio.to_thread.run_sync(handle.close)
    return size, digest.hexdigest()


def sha256_of_file(path: Path) -> str:
    """Return the SHA256 digest of a file on disk."""

    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(BLOCK_SIZE), b""):
            digest.update(block)
    return digest.hexdigest()


def remove_file(path: Path) -> None:
    """Delete a file and ignore the case where it is already gone."""

    path.unlink(missing_ok=True)


def remove_empty_parents(path: Path, stop_at: Path) -> None:
    """Remove the empty directories between ``path`` and ``stop_at``.

    Used to clean up the temporary directory after a failed upload.
    """

    stop_at = stop_at.resolve()
    current = path.resolve().parent
    while current != stop_at and stop_at in current.parents:
        try:
            current.rmdir()
        except OSError:
            break
        current = current.parent


def move_into(source: Path, destination: Path) -> None:
    """Move a finished file to its final place without overwriting anything.

    A hard link is used when the file system supports it: creating the link
    fails when the destination already exists, so the check and the move
    happen as one atomic step and an existing revision can never be replaced.
    """

    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.link(source, destination)
    except FileExistsError as exc:
        raise ConflictException("目标文件已存在，拒绝覆盖") from exc
    except OSError:
        # File systems without hard link support fall back to a checked move.
        if destination.exists():
            raise ConflictException("目标文件已存在，拒绝覆盖") from None
        shutil.move(str(source), str(destination))
        return
    remove_file(source)
