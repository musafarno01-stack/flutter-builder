
"""Application entry point."""

from __future__ import annotations

import logging
import sys

from PySide6.QtWidgets import QApplication

from flutter_project_maker import __version__
from flutter_project_maker.ui.main_window import MainWindow


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    logging.getLogger(__name__).info(
        "Starting Flutter Project Maker %s", __version__
    )

    app = QApplication(sys.argv)
    app.setApplicationName("Flutter Project Maker")
    app.setApplicationVersion(__version__)

    window = MainWindow()
    window.show()

    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
