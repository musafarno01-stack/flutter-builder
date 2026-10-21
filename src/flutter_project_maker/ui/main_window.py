
"""PySide6 desktop interface."""

from __future__ import annotations

import logging
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFileDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from flutter_project_maker.core.project_generator import (
    generate_project,
    validate_application_id,
    validate_project_name,
)
from flutter_project_maker.core.zip_manager import create_project_zip

logger = logging.getLogger(__name__)


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Flutter Project Maker")
        self.resize(960, 760)

        self.source_path: Path | None = None
        self.project_path: Path | None = None

        root = QWidget()
        layout = QVBoxLayout(root)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(16)

        heading = QLabel("Flutter Project Maker")
        heading.setObjectName("heading")
        subtitle = QLabel(
            "Turn a single Dart entry-point file into an Android Flutter project."
        )
        subtitle.setObjectName("subtitle")
        layout.addWidget(heading)
        layout.addWidget(subtitle)

        input_frame = QFrame()
        input_frame.setObjectName("panel")
        input_layout = QVBoxLayout(input_frame)

        self.file_label = QLabel("No Dart file selected")
        self.file_label.setWordWrap(True)
        choose_file = QPushButton("Choose Dart file…")
        choose_file.clicked.connect(self.choose_source)

        file_row = QHBoxLayout()
        file_row.addWidget(self.file_label, 1)
        file_row.addWidget(choose_file)
        input_layout.addLayout(file_row)

        form = QFormLayout()
        self.name_input = QLineEdit("my_flutter_app")
        self.app_id_input = QLineEdit("com.example.my_flutter_app")
        self.output_input = QLineEdit(str(Path.home() / "FlutterProjects"))

        choose_output = QPushButton("Browse…")
        choose_output.clicked.connect(self.choose_output)
        output_row = QHBoxLayout()
        output_row.addWidget(self.output_input, 1)
        output_row.addWidget(choose_output)

        form.addRow("Project name", self.name_input)
        form.addRow("Android application ID", self.app_id_input)
        form.addRow("Output directory", output_row)
        input_layout.addLayout(form)
        layout.addWidget(input_frame)

        self.generate_button = QPushButton("Generate Flutter project")
        self.generate_button.setObjectName("primaryButton")
        self.generate_button.clicked.connect(self.generate)
        layout.addWidget(self.generate_button)

        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        layout.addWidget(self.progress)

        self.status_label = QLabel("Select a Dart file to begin.")
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)

        report_title = QLabel("Analysis and validation report")
        report_title.setObjectName("sectionHeading")
        layout.addWidget(report_title)

        self.report = QPlainTextEdit()
        self.report.setReadOnly(True)
        self.report.setPlaceholderText(
            "Source analysis, generation warnings, and validation results will appear here."
        )
        layout.addWidget(self.report, 1)

        buttons = QHBoxLayout()
        self.open_folder_button = QPushButton("Open project location")
        self.open_folder_button.clicked.connect(self.open_project_location)
        self.open_folder_button.setEnabled(False)

        self.zip_button = QPushButton("Save project ZIP…")
        self.zip_button.setObjectName("primaryButton")
        self.zip_button.clicked.connect(self.save_zip)
        self.zip_button.setEnabled(False)

        buttons.addWidget(self.open_folder_button)
        buttons.addStretch(1)
        buttons.addWidget(self.zip_button)
        layout.addLayout(buttons)

        self.setCentralWidget(root)
        self.setStyleSheet(
            """
            QMainWindow { background: #f4f6fa; }
            QWidget { color: #182230; font-size: 13px; }
            QLabel#heading { font-size: 28px; font-weight: 700; }
            QLabel#subtitle { color: #5b6575; font-size: 14px; }
            QLabel#sectionHeading { font-size: 16px; font-weight: 600; }
            QFrame#panel {
                background: white;
                border: 1px solid #dce2eb;
                border-radius: 12px;
            }
            QLineEdit, QPlainTextEdit {
                background: white;
                border: 1px solid #cbd3df;
                border-radius: 6px;
                padding: 9px;
                selection-background-color: #235ee7;
            }
            QPlainTextEdit {
                font-family: Consolas, monospace;
                font-size: 12px;
            }
            QPushButton {
                background: white;
                border: 1px solid #cbd3df;
                border-radius: 7px;
                padding: 10px 14px;
            }
            QPushButton:hover { background: #edf2ff; }
            QPushButton:disabled { color: #8b95a5; }
            QPushButton#primaryButton {
                background: #2458d3;
                border: 1px solid #2458d3;
                color: white;
                font-weight: 600;
            }
            QPushButton#primaryButton:hover { background: #1947b6; }
            QProgressBar {
                border: 0;
                border-radius: 4px;
                height: 8px;
                background: #dfe5ef;
                text-visible: false;
            }
            QProgressBar::chunk {
                border-radius: 4px;
                background: #2458d3;
            }
            """
        )

    def choose_source(self) -> None:
        filename, _ = QFileDialog.getOpenFileName(
            self,
            "Select Dart entry-point file",
            str(Path.home()),
            "Dart source (*.dart)",
        )
        if filename:
            self.source_path = Path(filename)
            self.file_label.setText(str(self.source_path))
            if self.name_input.text() == "my_flutter_app":
                self.name_input.setText(
                    self.source_path.stem.lower().replace("-", "_")
                )

    def choose_output(self) -> None:
        directory = QFileDialog.getExistingDirectory(
            self, "Choose output directory", self.output_input.text()
        )
        if directory:
            self.output_input.setText(directory)

    def generate(self) -> None:
        if self.source_path is None:
            QMessageBox.warning(self, "Dart file required", "Choose a Dart file first.")
            return

        try:
            name = validate_project_name(self.name_input.text())
            app_id = validate_application_id(self.app_id_input.text())
            output = Path(self.output_input.text()).expanduser()
            if not output.is_absolute():
                raise ValueError("Choose an absolute output directory.")
            if not output.exists() and not output.parent.exists():
                raise ValueError("The output directory and its parent do not exist.")
        except (ValueError, OSError) as exc:
            QMessageBox.warning(self, "Check project settings", str(exc))
            return

        self.generate_button.setEnabled(False)
        self.zip_button.setEnabled(False)
        self.open_folder_button.setEnabled(False)
        self.progress.setValue(10)
        self.status_label.setText("Analyzing source and creating Android scaffolding…")
        self.report.clear()

        try:
            self.project_path, analysis = generate_project(
                self.source_path, output, name, app_id
            )
            self.progress.setValue(100)
            self.status_label.setText(
                f"Project generated: {self.project_path}"
            )
            self.report.setPlainText(
                self._format_analysis(analysis)
                + "\n\nGeneration completed with the warnings shown above."
                + "\n\nNote: dependency resolution and flutter analyze were not run."
            )
            self.zip_button.setEnabled(True)
            self.open_folder_button.setEnabled(True)
        except Exception as exc:
            logger.exception("Project generation failed")
            self.progress.setValue(0)
            self.status_label.setText("Generation failed.")
            self.report.setPlainText(f"{type(exc).__name__}: {exc}")
            QMessageBox.critical(self, "Generation failed", str(exc))
        finally:
            self.generate_button.setEnabled(True)

    @staticmethod
    def _format_analysis(analysis) -> str:
        lines = [
            f"Source: {analysis.source_file}",
            f"Entry point detected: {'yes' if analysis.has_main else 'no'}",
            "",
            "Imports:",
        ]
        lines.extend(f"  • {item}" for item in analysis.imports)
        if not analysis.imports:
            lines.append("  (none detected)")

        lines.extend(["", "Detected widgets:"])
        lines.extend(f"  • {item}" for item in analysis.widgets)
        if not analysis.widgets:
            lines.append("  (none detected)")

        lines.extend(["", "Issues and warnings:"])
        if analysis.issues:
            for issue in analysis.issues:
                lines.append(f"[{issue.severity.upper()}] {issue.message}")
                if issue.suggestion:
                    lines.append(f"  Suggested action: {issue.suggestion}")
        else:
            lines.append("No issues detected by the initial static checks.")

        lines.append(
            "\nStatic inspection is not a Dart parser and does not guarantee compilation."
        )
        return "\n".join(lines)

    def save_zip(self) -> None:
        if self.project_path is None or not self.project_path.is_dir():
            QMessageBox.warning(self, "No generated project", "Generate a project first.")
            return

        default_path = str(self.project_path.parent / f"{self.project_path.name}.zip")
        filename, _ = QFileDialog.getSaveFileName(
            self,
            "Save generated project ZIP",
            default_path,
            "ZIP archive (*.zip)",
        )
        if not filename:
            return

        target = Path(filename)
        if target.suffix.lower() != ".zip":
            target = target.with_suffix(".zip")

        try:
            saved = create_project_zip(self.project_path, target)
        except (OSError, ValueError, zipfile_error_types()) as exc:
            logger.exception("ZIP export failed")
            QMessageBox.critical(self, "ZIP export failed", str(exc))
            return

        self.status_label.setText(f"Verified ZIP saved to: {saved}")
        QMessageBox.information(
            self,
            "ZIP verified",
            f"The project archive was created and verified:\n{saved}",
        )

    def open_project_location(self) -> None:
        if self.project_path is None or not self.project_path.is_dir():
            return

        # Use the desktop's file manager; no shell command is constructed.
        import os
        import subprocess
        import sys

        try:
            if sys.platform == "win32":
                os.startfile(str(self.project_path.parent))  # type: ignore[attr-defined]
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(self.project_path.parent)])
            else:
                subprocess.Popen(["xdg-open", str(self.project_path.parent)])
        except OSError as exc:
            QMessageBox.warning(self, "Could not open folder", str(exc))


def zipfile_error_types() -> tuple[type[Exception], ...]:
    """Return expected archive errors without hiding unexpected programming errors."""
    import zipfile

    return (zipfile.BadZipFile, zipfile.LargeZipFile)
