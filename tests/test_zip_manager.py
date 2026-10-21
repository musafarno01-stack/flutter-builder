
import zipfile
from pathlib import Path

import pytest

from flutter_project_maker.core.zip_manager import create_project_zip


def test_creates_and_verifies_archive(tmp_path: Path) -> None:
    project = tmp_path / "My Flutter 项目"
    project.mkdir()
    (project / "README.md").write_text("Hello", encoding="utf-8")
    (project / "lib").mkdir()
    (project / "lib" / "main.dart").write_text(
        "void main() {}", encoding="utf-8"
    )

    archive_path = tmp_path / "output.zip"
    result = create_project_zip(project, archive_path)

    assert result == archive_path
    with zipfile.ZipFile(result) as archive:
        assert archive.testzip() is None
        assert f"{project.name}/README.md" in archive.namelist()
        assert f"{project.name}/lib/main.dart" in archive.namelist()


def test_excludes_python_caches(tmp_path: Path) -> None:
    project = tmp_path / "project"
    cache = project / "__pycache__"
    cache.mkdir(parents=True)
    (cache / "junk.pyc").write_bytes(b"junk")
    (project / "main.dart").write_text("void main() {}", encoding="utf-8")

    archive_path = tmp_path / "output.zip"
    create_project_zip(project, archive_path)

    with zipfile.ZipFile(archive_path) as archive:
        assert all("__pycache__" not in name for name in archive.namelist())


def test_rejects_empty_project(tmp_path: Path) -> None:
    project = tmp_path / "empty"
    project.mkdir()

    with pytest.raises(ValueError, match="no files"):
        create_project_zip(project, tmp_path / "empty.zip")


def test_rejects_destination_inside_project(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    (project / "main.dart").write_text("void main() {}", encoding="utf-8")

    with pytest.raises(ValueError, match="outside"):
        create_project_zip(project, project / "nested.zip")
