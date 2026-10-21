
from pathlib import Path

import pytest

from flutter_project_maker.core.analyzer import analyze_dart


def test_detects_imports_entry_point_and_widgets(tmp_path: Path) -> None:
    source = tmp_path / "main.dart"
    source.write_text(
        """
import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;

// import 'package:ignored/ignored.dart';
void main() {
  runApp(MaterialApp(home: Scaffold(body: Center(child: Text('Hello')))));
}
""",
        encoding="utf-8",
    )

    result = analyze_dart(source)

    assert result.has_main
    assert "package:flutter/material.dart" in result.sdk_imports
    assert "http" in result.package_imports
    assert "ignored" not in result.package_imports
    assert "MaterialApp" in result.widgets
    assert "Scaffold" in result.widgets
    assert "Text" in result.widgets


def test_reports_missing_local_import(tmp_path: Path) -> None:
    source = tmp_path / "main.dart"
    source.write_text("import 'screens/home.dart';\nvoid main() {}", encoding="utf-8")

    result = analyze_dart(source)

    assert "screens/home.dart" in result.unresolved_local_imports
    assert any(issue.code == "MISSING_LOCAL_IMPORT" for issue in result.issues)


def test_rejects_empty_file(tmp_path: Path) -> None:
    source = tmp_path / "main.dart"
    source.write_text("  \n", encoding="utf-8")

    with pytest.raises(ValueError, match="empty"):
        analyze_dart(source)


def test_rejects_non_dart_file(tmp_path: Path) -> None:
    source = tmp_path / "main.txt"
    source.write_text("void main() {}", encoding="utf-8")

    with pytest.raises(ValueError, match="\\.dart"):
        analyze_dart(source)


def test_rejects_invalid_utf8(tmp_path: Path) -> None:
    source = tmp_path / "main.dart"
    source.write_bytes(b"\xff\xfe\xfa")

    with pytest.raises(ValueError, match="UTF-8"):
        analyze_dart(source)


def test_does_not_detect_imports_inside_strings_or_comments(tmp_path: Path) -> None:
    source = tmp_path / "main.dart"
    source.write_text(
        """
// import 'package/commented/commented.dart';
void main() {
  final text = "import 'package/stringed/stringed.dart';";
}
""",
        encoding="utf-8",
    )

    result = analyze_dart(source)

    assert result.package_imports == []


def test_preserves_original_source(tmp_path: Path) -> None:
    source = tmp_path / "main.dart"
    original = b"void main() { print('original'); }\n"
    source.write_bytes(original)

    analyze_dart(source)

    assert source.read_bytes() == original
