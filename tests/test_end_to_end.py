
import json
import zipfile
from pathlib import Path

from flutter_project_maker.core.analyzer import analyze_dart
from flutter_project_maker.core.zip_manager import create_project_zip


def test_analyze_report_and_archive_round_trip(tmp_path: Path) -> None:
    source = tmp_path / "main.dart"
    source.write_text(
        "import 'package:flutter/material.dart';\n"
        "void main() { runApp(const MaterialApp(home: Text('Hello'))); }\n",
        encoding="utf-8",
    )

    result = analyze_dart(source)
    assert result.has_main

    project = tmp_path / "generated"
    (project / "lib").mkdir(parents=True)
    (project / "lib" / "main.dart").write_bytes(source.read_bytes())
    (project / "project-generation-report.json").write_text(
        json.dumps(result.to_dict()), encoding="utf-8"
    )

    archive_path = create_project_zip(project, tmp_path / "generated.zip")

    extraction = tmp_path / "extracted"
    with zipfile.ZipFile(archive_path) as archive:
        assert archive.testzip() is None
        archive.extractall(extraction)

    assert (
        extraction / "generated" / "lib" / "main.dart"
    ).read_bytes() == source.read_bytes()
    assert (
        extraction / "generated" / "project-generation-report.json"
    ).is_file()
