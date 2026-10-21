
"""Safe first-stage Flutter Android project generation."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

import yaml

from flutter_project_maker.core.analyzer import AnalysisResult, analyze_dart


PROJECT_NAME_RE = re.compile(r"^[a-z][a-z0-9_]{1,48}$")
APP_ID_RE = re.compile(
    r"^[a-zA-Z][a-zA-Z0-9_]*(?:\.[a-zA-Z][a-zA-Z0-9_]*)+$"
)


class GenerationError(RuntimeError):
    """A project could not be generated safely."""


def validate_project_name(name: str) -> str:
    name = name.strip()
    if not PROJECT_NAME_RE.fullmatch(name):
        raise ValueError(
            "Project name must contain 2–49 lowercase letters, digits, "
            "or underscores, and start with a letter."
        )
    return name


def validate_application_id(application_id: str) -> str:
    application_id = application_id.strip()
    if not APP_ID_RE.fullmatch(application_id):
        raise ValueError(
            "Application ID must contain at least two dot-separated "
            "identifier parts, such as com.example.my_app."
        )
    return application_id


def _patch_android_application_id(project: Path, application_id: str) -> None:
    """Patch generated Gradle namespace/application ID without replacing files."""
    candidates = list((project / "android" / "app").glob("build.gradle*"))
    if not candidates:
        raise GenerationError("Flutter template has no Android app Gradle file.")

    found = False
    for path in candidates:
        text = path.read_text(encoding="utf-8")
        updated = text

        for key in ("namespace", "applicationId"):
            pattern = rf'(\b{key}\s*[=(]\s*["\'])[^"\']+(["\'])'
            updated, count = re.subn(
                pattern,
                lambda match: match.group(1) + application_id + match.group(2),
                updated,
            )
            found = found or count > 0

        if updated != text:
            path.write_text(updated, encoding="utf-8")

    if not found:
        raise GenerationError(
            "Could not safely locate namespace/applicationId in generated Gradle files."
        )


def generate_project(
    source_file: str | Path,
    output_parent: str | Path,
    project_name: str,
    application_id: str,
) -> tuple[Path, AnalysisResult]:
    """Generate a project in a new directory and return its path and analysis."""
    source = Path(source_file).expanduser().resolve(strict=True)
    parent = Path(output_parent).expanduser().resolve()
    name = validate_project_name(project_name)
    app_id = validate_application_id(application_id)

    if source.suffix.lower() != ".dart" or not source.is_file():
        raise ValueError("Choose one existing .dart source file.")

    # Analyze before creating anything. Never execute uploaded Dart code.
    analysis = analyze_dart(source)

    flutter = shutil.which("flutter")
    if not flutter:
        raise GenerationError(
            "Flutter CLI was not found. Install Flutter and add its bin directory "
            "to PATH. This initial generator requires the local CLI."
        )

    parent.mkdir(parents=True, exist_ok=True)
    destination = parent / name
    if destination.exists():
        raise FileExistsError(
            f"Output already exists: {destination}. Choose another name or location."
        )

    # Read source bytes before generation so source data stays unchanged.
    original_bytes = source.read_bytes()

    with tempfile.TemporaryDirectory(prefix="flutter_project_maker_",
                                     dir=parent) as temp_dir:
        staging = Path(temp_dir) / name
        command = [
            flutter,
            "create",
            "--no-pub",
            "--platforms=android",
            "--project-name",
            name,
            "--org",
            app_id.rsplit(".", 1)[0],
            str(staging),
        ]

        try:
            completed = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=180,
                check=False,
                shell=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise GenerationError("Flutter project scaffolding timed out.") from exc
        except OSError as exc:
            raise GenerationError(f"Could not launch Flutter: {exc}") from exc

        if completed.returncode != 0 or not staging.is_dir():
            details = (completed.stderr or completed.stdout or "").strip()
            raise GenerationError(
                "Flutter could not create the Android template."
                + (f"\nDetails: {details[-2500:]}" if details else "")
            )

        lib = staging / "lib"
        lib.mkdir(parents=True, exist_ok=True)
        (lib / "main.dart").write_bytes(original_bytes)

        _patch_android_application_id(staging, app_id)

        (staging / "assets" / "images").mkdir(parents=True, exist_ok=True)
        (staging / "assets" / "fonts").mkdir(parents=True, exist_ok=True)

        pubspec_path = staging / "pubspec.yaml"
        try:
            pubspec = yaml.safe_load(pubspec_path.read_text(encoding="utf-8"))
        except (OSError, yaml.YAMLError) as exc:
            raise GenerationError(f"Generated pubspec.yaml is invalid: {exc}") from exc

        if not isinstance(pubspec, dict):
            raise GenerationError("Generated pubspec.yaml has an unexpected structure.")

        # Do not invent versions for imported third-party packages.
        pubspec["name"] = name
        pubspec_path.write_text(
            yaml.safe_dump(pubspec, sort_keys=False, allow_unicode=True),
            encoding="utf-8",
        )

        unresolved = list(analysis.unresolved_local_imports)
        missing_assets = list(analysis.asset_references)

        report = {
            "generator": "Flutter Project Maker",
            "generator_version": "0.1.0",
            "project_name": name,
            "application_id": app_id,
            "source_file": source.name,
            "source_preserved_as": "lib/main.dart",
            "analysis": analysis.to_dict(),
            "validation": {
                "flutter_create": "passed",
                "source_copy": (lib / "main.dart").read_bytes() == original_bytes,
                "pubspec_yaml": "passed",
                "third_party_dependency_resolution": (
                    "not_performed; review package imports"
                ),
                "flutter_analyze": "not_performed",
                "apk_or_aab_build": "not_performed",
            },
            "unresolved_local_imports": unresolved,
            "asset_references_requiring_review": missing_assets,
            "warnings": [
                "Generation uses the locally installed Flutter CLI, not a bundled template.",
                "Third-party package versions have not been resolved.",
                "Only the supplied Dart file is copied; missing application files are not fabricated.",
                "Flutter analyze and dependency resolution have not been run.",
            ],
        }

        (staging / "project-generation-report.json").write_text(
            json.dumps(report, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

        readme = f"""# {name}

Generated by Flutter Project Maker.

## Android application ID

`{app_id}`

## Source limitations

The supplied Dart file was copied to `lib/main.dart` unchanged.
Additional Dart files, images, fonts, credentials, and service configuration
were not inferred or fabricated.

Review `project-generation-report.json` before running the app.

## Validate locally

Install a compatible Flutter SDK, then run:

```sh
flutter pub get
dart analyze
```

No APK or AAB was built during generation.
"""
        (staging / "README.md").write_text(readme, encoding="utf-8")

        # Rename only after all required files are written.
        staging.rename(destination)

    return destination, analysis
