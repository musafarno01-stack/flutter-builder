
# Flutter Project Maker

Flutter Project Maker is a Python desktop application for generating an Android Flutter project from a single Dart entry-point file.

## Current implementation status

The initial implementation includes:

- A PySide6 desktop interface.
- UTF-8 and file-size validation.
- Conservative Dart import and widget inspection.
- Missing local-import detection.
- Android project scaffolding through the locally installed Flutter CLI.
- Preservation of the supplied file as `lib/main.dart`.
- Android application ID configuration.
- Generation of a JSON report.
- ZIP creation and integrity verification.
- Initial automated tests.

Not implemented yet: bundled offline Android templates, full Dart parsing, verified third-party dependency resolution, launcher icon processing, advertising integrations, drag-and-drop, and optional Flutter analysis. These features must not be considered complete until implemented and tested.

## Requirements

- Python 3.12 or another compatible version supported by the dependencies.
- Flutter SDK installed locally and available on `PATH`.
- A supported desktop environment for PySide6.
- Internet access may be required by Flutter when resolving dependencies, but the current generator uses `flutter create --no-pub`.

The Python application itself does not upload source code or use cloud AI services.

## Installation

Create and activate a virtual environment.

### Windows

```powershell
py -3.12 -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -e ".[dev]"
```

### Linux or macOS

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -e ".[dev]"
```

## Launch

```bash
flutter-project-maker
```

Alternatively:

```bash
python -m flutter_project_maker.main
```

## Usage

1. Open Flutter Project Maker.
2. Select a `.dart` file.
3. Enter a valid project name and Android application ID.
4. Choose the parent output directory.
5. Generate the project.
6. Review the analysis report and generated JSON report.
7. Use **Save project ZIP** to choose an archive destination.

The generator refuses to overwrite an existing project directory.

## Project validation

From the generated project directory:

```bash
flutter pub get
dart analyze
```

These commands are not automatically run by the current generator. Dependency resolution may require network access.

No APK or AAB build is part of ordinary generation.

## Tests and quality checks

```bash
pytest
ruff check .
ruff format --check .
mypy src/flutter_project_maker
```

## Single-file limitations

A Dart file may depend on custom classes, additional source files, images, fonts, credentials, and native configuration that are not present in the input. The analyzer reports some missing references but cannot reconstruct missing application logic.

The initial analyzer is not a complete Dart parser. A clean static report does not guarantee compilation or runtime correctness.

## Security

- Uploaded Dart code is never executed.
- Flutter is invoked using a list of command arguments, not a shell command assembled from user input.
- Generated output directories are checked before creation.
- ZIP archives are checked for integrity before the application reports success.
- Do not put production secrets in source code or generated archives.

## Development status

This repository is being implemented in stages. Check the source, tests, and generation report to determine which capabilities are actually available in a given version.
