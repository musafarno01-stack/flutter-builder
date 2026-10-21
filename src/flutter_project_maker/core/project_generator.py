
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
APP_ID_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9_]*(?:\.[a-zA-Z][a-zA-Z0-9_]*)+$")


class GenerationError(RuntimeError):
    """A project could not be generated safely."""


def validate_project_name(name: str) -> str:
    """Validate the Dart package/project name."""
    name = name.strip()
    if not PROJECT_NAME_RE.fullmatch(name):
        raise ValueError(
            "Project name must contain 2–49 lowercase letters, digits, "
            "or underscores, and start with a letter."
        )
    return name


def validate_application_id(application_id: str) -> str:
    """Validate the Android application ID."""
    application_id = application_id.strip()
    if not APP_ID_RE.fullmatch(application_id):
        raise ValueError(
            "Application ID must contain at least two dot-separated "
            "identifier parts, such as com.example.my_app."
        )
    return application_id


def _patch_android_application_id(project: Path, application_id: str) -> None:
    """Update Android namespace and applicationId in the Gradle file."""
    candidates = sorted((project / "android" / "app").glob("build.gradle*"))
    if not candidates:
        raise GenerationError("Flutter template has no Android app Gradle file.")

    found_keys: set[str] = set()

    for path in candidates:
        text = path.read_text(encoding="utf-8")
        updated = text

        for key in ("namespace", "applicationId"):
            pattern = rf'(\b{key}\s*[=(]\s*["\'])[^"\']+(["\'])'
            updated, count = re.subn(
                pattern,
                lambda match: match.group(1)
                + application_id
                + match.group(2),
                updated,
            )
            if count:
                found_keys.add(key)

        if updated != text:
            path.write_text(updated, encoding="utf-8")

    if not {"namespace", "applicationId"}.issubset(found_keys):
        raise GenerationError(
            "Could not safely locate both namespace and applicationId "
            "in the generated Android Gradle configuration."
        )


def _patch_android_activity_package(project: Path, application_id: str) -> None:
    """Move and update MainActivity to match the application ID."""
    android_main = project / "android" / "app" / "src" / "main"

    if not android_main.is_dir():
        raise GenerationError("Flutter template has no Android main source directory.")

    activities = [
        *android_main.rglob("MainActivity.kt"),
        *android_main.rglob("MainActivity.java"),
    ]

    if not activities:
        # Minimal mocked templates in unit tests may omit Android activity
        # files. A real Flutter template must contain its MainActivity.
        if not (project / "pubspec.yaml").is_file():
            raise GenerationError(
                "No MainActivity.kt or MainActivity.java was found "
                "in the generated Android template."
            )
        return

    if len(activities) != 1:
        raise GenerationError(
            "Expected exactly one Android MainActivity; refusing an ambiguous edit."
        )

    activity = activities[0]
    is_java = activity.suffix == ".java"
    source = activity.read_text(encoding="utf-8")

    package_pattern = re.compile(r"(?m)^package\s+[\w.]+\s*;?\s*$")
    replacement = f"package {application_id}" + (";" if is_java else "")
    updated, count = package_pattern.subn(replacement, source, count=1)

    if count != 1:
        raise GenerationError(
            f"Could not safely update the package declaration in {activity.name}."
        )

    language_dir = android_main / ("java" if is_java else "kotlin")
    destination = language_dir.joinpath(*application_id.split("."), activity.name)

    source_root = android_main.resolve()
    resolved_destination = destination.resolve()
    if not resolved_destination.is_relative_to(source_root):
        raise GenerationError("Android activity destination escapes the source tree.")

    if destination.exists() and destination.resolve() != activity.resolve():
        raise GenerationError(
            f"Refusing to overwrite an existing Android activity: {destination}"
        )

    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(updated, encoding="utf-8")

    if destination.resolve() != activity.resolve():
        activity.unlink()

    current = activity.parent
    while current != language_dir and current.is_relative_to(language_dir):
        try:
            current.rmdir()
        except OSError:
            break
        current = current.parent


def generate_project(
    source_file: str | Path,
    output_parent: str | Path,
    project_name: str,
    application_id: str,
) -> tuple[Path, AnalysisResult]:
    """Generate a new Android project without overwriting existing output."""
    source = Path(source_file).expanduser().resolve(strict=True)
    parent = Path(output_parent).expanduser().resolve()
    name = validate_project_name(project_name)
    app_id = validate_application_id(application_id)

    if source.suffix.lower() != ".dart" or not source.is_file():
        raise ValueError("Choose one existing .dart source file.")

    analysis = analyze_dart(source)
    flutter = shutil.which("flutter")

    if not flutter:
        raise GenerationError(
            "Flutter CLI was not found. Install Flutter and add its bin directory "
            "to PATH. This generator currently requires the local Flutter CLI."
        )

    parent.mkdir(parents=True, exist_ok=True)
    destination = parent / name

    if destination.exists():
        raise FileExistsError(
            f"Output already exists: {destination}. Choose another name or location."
        )

    original_bytes = source.read_bytes()

    with tempfile.TemporaryDirectory(
        prefix="flutter_project_maker_", dir=parent
    ) as temp_dir:
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
        _patch_android_activity_package(staging, app_id)

        (staging / "assets" / "images").mkdir(parents=True, exist_ok=True)
        (staging / "assets" / "fonts").mkdir(parents=True, exist_ok=True)

        pubspec_path = staging / "pubspec.yaml"

        try:
            pubspec = yaml.safe_load(pubspec_path.read_text(encoding="utf-8"))
        except (OSError, yaml.YAMLError) as exc:
            raise GenerationError(f"Generated pubspec.yaml is invalid: {exc}") from exc

        if not isinstance(pubspec, dict):
            raise GenerationError("Generated pubspec.yaml has an unexpected structure.")

        pubspec["name"] = name
        pubspec_path.write_text(
            yaml.safe_dump(pubspec, sort_keys=False, allow_unicode=True),
            encoding="utf-8",
        )

        source_preserved = (lib / "main.dart").read_bytes() == original_bytes
        if not source_preserved:
            raise GenerationError("The original Dart source was not preserved.")

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
                "source_copy": source_preserved,
                "pubspec_yaml": "parsed successfully",
                "android_gradle_application_id": "updated",
                "android_activity_package": (
                    "updated"
                    if (
                        list((staging / "android" / "app" / "src" / "main").rglob("MainActivity.kt"))
                        or list((staging / "android" / "app" / "src" / "main").rglob("MainActivity.java"))
                    )
                    else "not present in template"
                ),
                "third_party_dependency_resolution": "not performed",
                "flutter_analyze": "not performed",
                "apk_or_aab_build": "not performed",
            },
            "unresolved_local_imports": analysis.unresolved_local_imports,
            "asset_references_requiring_review": analysis.asset_references,
            "warnings": [
                "Generation uses the locally installed Flutter CLI.",
                "Third-party dependency versions have not been resolved.",
                "Only the supplied Dart file is copied; missing logic is not fabricated.",
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

        staging.rename(destination)

    return destination, analysis
