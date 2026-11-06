"""Policy for the file types the artifact storage accepts.

Two independent checks protect the platform:

* the **extension** decides which kind of file is allowed at all,
* the **content** has to match that extension, so a renamed executable cannot
  slip through as a PDF.

The client supplied ``Content-Type`` header is deliberately ignored - it is
untrusted input. The canonical media type is derived from the extension and
stored in the database.
"""

from __future__ import annotations

import codecs
import json
import zipfile
from pathlib import Path

from app.core.exceptions import ValidationException
from app.core.storage import BLOCK_SIZE

#: Canonical media type per accepted extension.
EXTENSION_MIME_TYPES: dict[str, str] = {
    "pdf": "application/pdf",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "md": "text/markdown",
    "markdown": "text/markdown",
    "txt": "text/plain",
    "json": "application/json",
    "yaml": "application/yaml",
    "yml": "application/yaml",
}

#: Extensions whose content is a plain UTF-8 text file.
_TEXT_EXTENSIONS = {"md", "markdown", "txt", "yaml", "yml"}

#: Magic prefix of a PDF document.
_PDF_MAGIC = b"%PDF-"


def extension_of(filename: str) -> str:
    """Return the lower case extension of a file name without the dot."""

    _, dot, extension = filename.rpartition(".")
    if not dot:
        return ""
    return extension.strip().lower()


def resolve_file_type(filename: str, allowed_extensions: frozenset[str]) -> str:
    """Return the canonical media type for a file name.

    Raises a validation error when the extension is not part of the whitelist.
    """

    extension = extension_of(filename)
    if not extension:
        raise ValidationException("文件缺少扩展名，无法判断类型")
    if extension not in allowed_extensions:
        raise ValidationException(f"不允许上传 .{extension} 类型的文件")
    mime_type = EXTENSION_MIME_TYPES.get(extension)
    if mime_type is None:
        raise ValidationException(f"不支持的文件类型: .{extension}")
    return mime_type


def verify_content(path: Path, extension: str) -> None:
    """Check that the content of the file matches its extension.

    The check runs on the finished file on disk, before it is moved to its
    final location and before any metadata is stored.
    """

    if extension == "pdf":
        _verify_pdf(path)
    elif extension == "docx":
        _verify_docx(path)
    elif extension == "json":
        _verify_json(path)
    elif extension in _TEXT_EXTENSIONS:
        _verify_text(path)
    else:  # pragma: no cover - the whitelist keeps this unreachable
        raise ValidationException(f"不支持的文件类型: .{extension}")


def _verify_pdf(path: Path) -> None:
    with path.open("rb") as handle:
        header = handle.read(len(_PDF_MAGIC))
    if header != _PDF_MAGIC:
        raise ValidationException("文件内容不是有效的 PDF")


def _verify_docx(path: Path) -> None:
    if not zipfile.is_zipfile(path):
        raise ValidationException("文件内容不是有效的 DOCX 文档")
    try:
        with zipfile.ZipFile(path) as archive:
            names = set(archive.namelist())
    except (zipfile.BadZipFile, OSError) as exc:
        raise ValidationException("文件内容不是有效的 DOCX 文档") from exc
    if "word/document.xml" not in names:
        raise ValidationException("文件内容不是有效的 DOCX 文档")


def _verify_text(path: Path) -> None:
    decoder = codecs.getincrementaldecoder("utf-8")()
    try:
        with path.open("rb") as handle:
            for block in iter(lambda: handle.read(BLOCK_SIZE), b""):
                if b"\x00" in block:
                    raise ValidationException("文本文件包含空字节，不是合法的文本内容")
                decoder.decode(block)
            decoder.decode(b"", final=True)
    except UnicodeDecodeError as exc:
        raise ValidationException("文本文件不是合法的 UTF-8 编码") from exc


def _verify_json(path: Path) -> None:
    try:
        content = path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise ValidationException("JSON 文件不是合法的 UTF-8 编码") from exc
    if "\x00" in content:
        raise ValidationException("JSON 文件包含空字节，不是合法内容")
    try:
        json.loads(content)
    except (ValueError, RecursionError) as exc:
        raise ValidationException("文件内容不是有效的 JSON") from exc
