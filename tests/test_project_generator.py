
import json
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from flutter_project_maker.core.project_generator import (
    generate_project,
    validate_application_id,
    validate_project_name,
)


def test_valid_project_name() -> None:
    assert validate_project_name("sample_app") == "sample_app"


@pytest.mark.parametrize("name", ["", "My App", "1app", "../escape", "a"])
def test_invalid_project_name(name: str) -> None:
    with pytest.raises(ValueError):
        validate_project_name(name)


def test_valid_application_id() -> None:
    assert validate_application_id("com.example.sample_app") == (
        "com.example.sample_app"
    )


@pytest.mark.parametrize(
    "app_id",
    [
        "",
        "example",
        ".example.app",
        "com..app",
        "../unsafe",
        "com.example bad.app",
    ],
)
def test_invalid_application_id(app_id: str) -> None:
    with pytest.raises(ValueError):
        validate_application_id(app_id)


def test_generation_preserves_source_and_writes_report(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "original.dart"
    original = b"import 'package:flutter/material.dart';\nvoid main() {}\n"
    source.write_bytes(original)

    output = tmp_path / "output"
    output.mkdir()

    monkeypatch.setattr(
        "flutter_project_maker.core.project_generator.shutil.which",
        lambda command: "/fake/flutter",
    )

    def fake_run(command, **kwargs):
        project = Path(command[-1])
        app = project / "android" / "app"
        app.mkdir(parents=True)
        (app / "build.gradle.kts").write_text(
            'android {\n'
            '    namespace = "com.example.old"\n'
            '    defaultConfig {\n'
            '        applicationId = "com.example.old"\n'
            '    }\n'
            '}\n',
            encoding="utf-8",
        )
        (project / "lib").mkdir()
        (project / "pubspec.yaml").write_text(
            "name: generated_app\n"
            "description: Test project\n"
            "publish_to: none\n"
            "version: 1.0.0+1\n"
            "environment:\n"
            "  sdk: '>=3.0.0 <4.0.0'\n"
            "dependencies:\n"
            "  flutter:\n"
            "    sdk: flutter\n"
            "dev_dependencies:\n"
            "  flutter_test:\n"
            "    sdk: flutter\n"
            "flutter:\n"
            "  uses-material-design: true\n",
            encoding="utf-8",
        )
        return SimpleNamespace(returncode=0, stdout="ok", stderr="")

    monkeypatch.setattr(
        "flutter_project_maker.core.project_generator.subprocess.run",
        fake_run,
    )

    project, analysis = generate_project(
        source,
        output,
        "sample_app",
        "com.example.sample_app",
    )

    assert source.read_bytes() == original
    assert (project / "lib" / "main.dart").read_bytes() == original
    assert (project / "README.md").is_file()
    assert (project / "project-generation-report.json").is_file()
    assert analysis.has_main

    report = json.loads(
        (project / "project-generation-report.json").read_text(
            encoding="utf-8"
        )
    )
    assert report["validation"]["source_copy"] is True

    gradle = (
        project / "android" / "app" / "build.gradle.kts"
    ).read_text(encoding="utf-8")
    assert gradle.count("com.example.sample_app") == 2


def test_existing_project_is_not_overwritten(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "main.dart"
    source.write_text("void main() {}", encoding="utf-8")

    output = tmp_path / "output"
    output.mkdir()
    existing = output / "sample_app"
    existing.mkdir()
    marker = existing / "important.txt"
    marker.write_text("keep me", encoding="utf-8")

    monkeypatch.setattr(
        "flutter_project_maker.core.project_generator.shutil.which",
        lambda command: "/fake/flutter",
    )

    with pytest.raises(FileExistsError):
        generate_project(
            source,
            output,
            "sample_app",
            "com.example.sample_app",
        )

    assert marker.read_text(encoding="utf-8") == "keep me"
