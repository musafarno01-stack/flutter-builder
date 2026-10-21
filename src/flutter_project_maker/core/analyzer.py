
"""Conservative, non-executing Dart source inspection."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from pathlib import Path

MAX_DART_BYTES = 5 * 1024 * 1024

_IMPORT_RE = re.compile(
    r"""(?m)^\s*import\s+(['"])(?P<uri>[^'"]+)\1\s*(?:[^;]*);"""
)
_EXPORT_RE = re.compile(
    r"""(?m)^\s*export\s+(['"])(?P<uri>[^'"]+)\1\s*(?:[^;]*);"""
)
_WIDGET_RE = re.compile(
    r"\b(MaterialApp|CupertinoApp|Scaffold|AppBar|Text|Center|"
    r"Column|Row|Container|Stack|ListView|GridView|"
    r"ElevatedButton|TextButton|IconButton|Image|Navigator)\s*\("
)
_ASSET_RE = re.compile(
    r"""(?:Image\.asset|AssetImage|rootBundle\.loadString|"""
    r"""rootBundle\.load|FontLoader)\s*\(\s*['"]([^'"]+)['"]"""
)
_ENTRY_RE = re.compile(r"\bvoid\s+main\s*\(")


@dataclass
class Issue:
    severity: str
    code: str
    message: str
    file: str = "main.dart"
    suggestion: str = ""


@dataclass
class AnalysisResult:
    source_file: str
    imports: list[str] = field(default_factory=list)
    sdk_imports: list[str] = field(default_factory=list)
    package_imports: list[str] = field(default_factory=list)
    local_imports: list[str] = field(default_factory=list)
    unresolved_local_imports: list[str] = field(default_factory=list)
    asset_references: list[str] = field(default_factory=list)
    widgets: list[str] = field(default_factory=list)
    has_main: bool = False
    issues: list[Issue] = field(default_factory=list)

    def to_dict(self) -> dict:
        """Return a JSON-serializable report."""
        return {
            **asdict(self),
            "issues": [asdict(issue) for issue in self.issues],
        }


def _remove_comments(source: str) -> str:
    """Remove comments while preserving strings and line structure.

    This scanner is not a complete Dart parser. Use dart analyze for
    syntax validation when the Dart SDK is installed.
    """
    output: list[str] = []
    i = 0
    state = "code"

    while i < len(source):
        char = source[i]
        nxt = source[i + 1] if i + 1 < len(source) else ""

        if state == "code":
            if char in ("'", '"'):
                triple = source.startswith(char * 3, i)
                marker = char * (3 if triple else 1)
                output.append(marker)
                i += len(marker)
                state = "triple" + char if triple else "string" + char
                continue

            if char == "/" and nxt == "/":
                output.extend((" ", " "))
                i += 2
                state = "line_comment"
                continue

            if char == "/" and nxt == "*":
                output.extend((" ", " "))
                i += 2
                state = "block_comment"
                continue

            output.append(char)
            i += 1
            continue

        if state.startswith("string") or state.startswith("triple"):
            quote = state[-1]
            marker = quote * (3 if state.startswith("triple") else 1)

            if char == "\\" and i + 1 < len(source):
                output.extend((char, source[i + 1]))
                i += 2
                continue

            if source.startswith(marker, i):
                output.append(marker)
                i += len(marker)
                state = "code"
                continue

            output.append(char)
            i += 1
            continue

        if state == "line_comment":
            if char == "\n":
                output.append("\n")
                state = "code"
            else:
                output.append(" ")
            i += 1
            continue

        if state == "block_comment":
            if char == "*" and nxt == "/":
                output.extend((" ", " "))
                i += 2
                state = "code"
            else:
                output.append("\n" if char == "\n" else " ")
                i += 1

    return "".join(output)


def analyze_dart(path: str | Path) -> AnalysisResult:
    """Inspect a Dart file without executing it."""
    source_path = Path(path)

    if source_path.suffix.lower() != ".dart":
        raise ValueError("Select a file with the .dart extension.")

    if not source_path.is_file():
        raise FileNotFoundError(f"Dart source file does not exist: {source_path}")

    if source_path.stat().st_size > MAX_DART_BYTES:
        raise ValueError("Dart source exceeds the 5 MiB file-size limit.")

    try:
        source = source_path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError("Dart source must be valid UTF-8.") from exc

    if not source.strip():
        raise ValueError("The selected Dart file is empty.")

    if "\x00" in source:
        raise ValueError("The selected file contains invalid NUL characters.")

    result = AnalysisResult(source_file=source_path.name)
    cleaned = _remove_comments(source)

    result.has_main = bool(_ENTRY_RE.search(cleaned))
    if not result.has_main:
        result.issues.append(
            Issue(
                "warning",
                "MAIN_NOT_FOUND",
                "No conventional void main() entry point was detected.",
                suggestion=(
                    "Confirm that this file is the application's entry point."
                ),
            )
        )

    source_root = source_path.parent.resolve()

    for match in _IMPORT_RE.finditer(cleaned):
        uri = match.group("uri")
        result.imports.append(uri)

        if uri.startswith(("dart:", "package:flutter/")):
            result.sdk_imports.append(uri)
        elif uri.startswith("package:"):
            package = uri.removeprefix("package:").split("/", 1)[0]
            if package != "flutter":
                result.package_imports.append(package)
        else:
            result.local_imports.append(uri)
            candidate = (source_path.parent / uri).resolve()

            if not candidate.is_relative_to(source_root):
                result.issues.append(
                    Issue(
                        "error",
                        "IMPORT_PATH_ESCAPE",
                        f"Local import escapes the source directory: {uri}",
                        suggestion=(
                            "Move the required source file into the project safely."
                        ),
                    )
                )
            elif not candidate.is_file():
                result.unresolved_local_imports.append(uri)
                result.issues.append(
                    Issue(
                        "warning",
                        "MISSING_LOCAL_IMPORT",
                        f"Referenced local Dart file was not supplied: {uri}",
                        suggestion=(
                            "Provide the missing file and its dependencies."
                        ),
                    )
                )

    for match in _EXPORT_RE.finditer(cleaned):
        uri = match.group("uri")
        if not uri.startswith(("dart:", "package:")):
            result.issues.append(
                Issue(
                    "warning",
                    "LOCAL_EXPORT_REVIEW",
                    f"Local export needs review: {uri}",
                    suggestion="Check whether the exported file is available.",
                )
            )

    result.widgets = list(dict.fromkeys(_WIDGET_RE.findall(cleaned)))
    result.asset_references = list(dict.fromkeys(_ASSET_RE.findall(cleaned)))

    result.imports = list(dict.fromkeys(result.imports))
    result.sdk_imports = list(dict.fromkeys(result.sdk_imports))
    result.package_imports = list(dict.fromkeys(result.package_imports))
    result.local_imports = list(dict.fromkeys(result.local_imports))

    if result.package_imports:
        result.issues.append(
            Issue(
                "warning",
                "DEPENDENCIES_REQUIRE_REVIEW",
                "Third-party packages were detected. Their compatible versions "
                "have not yet been resolved by a verified dependency registry.",
                suggestion=(
                    "Review package requirements before running flutter pub get."
                ),
            )
        )

    if result.asset_references:
        result.issues.append(
            Issue(
                "warning",
                "ASSETS_REQUIRE_REVIEW",
                "The source references assets or fonts that may not have been supplied.",
                suggestion=(
                    "Provide referenced resources and declare them in pubspec.yaml."
                ),
            )
        )

    return result
