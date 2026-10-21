
"""Safe ZIP packaging for generated Flutter projects."""

from __future__ import annotations

import os
import tempfile
import zipfile
from pathlib import Path, PurePosixPath


EXCLUDED_PARTS = {
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".git",
    ".dart_tool",
    "build",
}

SENSITIVE_NAMES = {
    ".env",
    ".env.local",
    ".env.production",
    "key.properties",
    "google-services.json",
    "service-account.json",
    "credentials.json",
}

SENSITIVE_SUFFIXES = {
    ".jks",
    ".keystore",
    ".p12",
    ".pfx",
    ".pem",
}


def _should_exclude(relative: Path) -> bool:
    """Return True for known caches or sensitive file names."""
    if any(part in EXCLUDED_PARTS for part in relative.parts):
        return True

    filename = relative.name.lower()

    if filename in SENSITIVE_NAMES:
        return True

    if filename.startswith(".env."):
        return True

    if Path(filename).suffix.lower() in SENSITIVE_SUFFIXES:
        return True

    return False


def create_project_zip(
    project_dir: str | Path,
    destination: str | Path,
) -> Path:
    """Create, verify, and save a ZIP without following symlinks."""
    project = Path(project_dir).expanduser().resolve(strict=True)
    target = Path(destination).expanduser().resolve()

    if not project.is_dir():
        raise ValueError("The generated project path must be a directory.")

    if target == project or project in target.parents:
        raise ValueError("The ZIP destination must be outside the project directory.")

    if target == project.parent:
        raise ValueError("The ZIP destination must be a file, not the project parent.")

    target.parent.mkdir(parents=True, exist_ok=True)

    if target.exists() and target.is_dir():
        raise IsADirectoryError(f"ZIP destination is a directory: {target}")

    files: list[Path] = []

    for item in project.rglob("*"):
        relative = item.relative_to(project)

        if _should_exclude(relative):
            continue

        if item.is_symlink():
            raise ValueError(
                f"Symbolic links are not allowed in project archives: {relative}"
            )

        if item.is_file():
            files.append(item)

    if not files:
        raise ValueError("The project directory contains no files to archive.")

    expected = {
        str(PurePosixPath(project.name, *item.relative_to(project).parts))
        for item in files
    }

    fd, temporary_name = tempfile.mkstemp(
        prefix="flutter_project_",
        suffix=".zip.tmp",
        dir=target.parent,
    )
    os.close(fd)
    temporary = Path(temporary_name)

    try:
        with zipfile.ZipFile(
            temporary,
            mode="w",
            compression=zipfile.ZIP_DEFLATED,
        ) as archive:
            for item in files:
                relative = item.relative_to(project)
                archive_name = PurePosixPath(project.name, *relative.parts)
                archive.write(item, str(archive_name))

        with zipfile.ZipFile(temporary, mode="r") as archive:
            bad_member = archive.testzip()

            if bad_member is not None:
                raise zipfile.BadZipFile(
                    f"ZIP verification failed: {bad_member}"
                )

            actual = set(archive.namelist())

            if actual != expected:
                raise zipfile.BadZipFile(
                    "ZIP contents do not match the filtered project files."
                )

        # Replacing the target is atomic on the same filesystem.
        os.replace(temporary, target)
        return target

    finally:
        temporary.unlink(missing_ok=True)
