"""Bounded yt-dlp wrapper for publicly accessible media URLs."""
from __future__ import annotations

import tempfile
from pathlib import Path

import yt_dlp

from url_utils import is_valid_url

MAX_BYTES = 48 * 1024 * 1024


class DownloadError(RuntimeError):
    """A download failed validation or could not be safely completed."""


def _enforce_download_limit(status: dict) -> None:
    """Abort when yt-dlp reports a download larger than the upload limit."""
    for key in ("downloaded_bytes", "total_bytes", "total_bytes_estimate"):
        size = status.get(key)
        if isinstance(size, (int, float)) and size > MAX_BYTES:
            raise DownloadError("File exceeds Telegram upload limit")


def _size_filter(info: dict, *, incomplete: bool = False):
    """Reject media whose known or estimated size exceeds the limit."""
    size = info.get("filesize")
    if not isinstance(size, (int, float)):
        size = info.get("filesize_approx")

    if isinstance(size, (int, float)) and size > MAX_BYTES:
        return "File exceeds Telegram upload limit"

    return None


def _inside_root(path: Path, root: Path) -> bool:
    """Return True only for resolved paths inside the isolated directory."""
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except (OSError, ValueError, RuntimeError):
        return False


def _find_output(info: dict, ydl, root: Path) -> Path:
    """Locate the final output, including postprocessed/merged media."""
    candidates = []

    # yt-dlp may expose the final postprocessed path here.
    filepath = info.get("filepath")
    if isinstance(filepath, str) and filepath:
        candidates.append(Path(filepath))

    # This can refer to the pre-merge filename, so it is only a candidate.
    try:
        candidates.append(Path(ydl.prepare_filename(info)))
    except (OSError, ValueError, KeyError):
        pass

    for candidate in candidates:
        try:
            resolved = candidate.resolve()
            if (
                _inside_root(resolved, root)
                and resolved.is_file()
                and not resolved.name.endswith((".part", ".ytdl"))
            ):
                return resolved
        except (OSError, RuntimeError):
            continue

    # Merged formats can have a different extension from the prepared name.
    files = []
    try:
        for item in root.iterdir():
            try:
                resolved = item.resolve()
                if (
                    _inside_root(resolved, root)
                    and resolved.is_file()
                    and not resolved.name.endswith((".part", ".ytdl"))
                ):
                    files.append(resolved)
            except (OSError, RuntimeError):
                continue
    except OSError as exc:
        raise DownloadError("Could not inspect download output") from exc

    # Fail closed instead of accidentally sending an intermediate file.
    unique_files = list(dict.fromkeys(files))
    if len(unique_files) != 1:
        raise DownloadError("Could not identify a single downloaded file")

    return unique_files[0]


def download_media(url: str) -> tuple[tempfile.TemporaryDirectory, Path]:
    """Download public media into an isolated directory.

    The caller is responsible for calling cleanup() on the returned
    TemporaryDirectory after the file has been sent or is no longer needed.
    """
    if not is_valid_url(url):
        raise DownloadError("URL rejected by security policy")

    temp = tempfile.TemporaryDirectory(prefix="whisky_")
    root = Path(temp.name).resolve()

    try:
        opts = {
            "outtmpl": str(root / "%(id)s.%(ext)s"),
            "noplaylist": True,
            "max_filesize": MAX_BYTES,
            "match_filter": _size_filter,
            "progress_hooks": [_enforce_download_limit],
            "quiet": True,
            "no_warnings": True,
            "socket_timeout": 20,
            "retries": 1,
            "fragment_retries": 1,
            "restrictfilenames": True,
            "overwrites": False,
            "cachedir": False,
            "paths": {
                "home": str(root),
                "temp": str(root),
            },
        }

        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
            if not info:
                raise DownloadError("No media information returned")

            filename = _find_output(info, ydl, root)

        if not _inside_root(filename, root) or not filename.is_file():
            raise DownloadError("Downloaded path failed validation")

        if filename.stat().st_size > MAX_BYTES:
            raise DownloadError("File exceeds Telegram upload limit")

        return temp, filename

    except Exception:
        temp.cleanup()
        raise
