from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from dayz_texture_tool.settings import load_settings
from dayz_texture_tool.ui import theme
from dayz_texture_tool.ui.shell import MainWindow


def main() -> None:
    app = QApplication(sys.argv[:1])
    app.setApplicationName("DayZ Texture Tool")
    settings = load_settings()
    theme.apply(app, settings.theme)
    window = MainWindow(settings)
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
