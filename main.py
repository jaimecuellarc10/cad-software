import sys
from PySide6.QtWidgets import QApplication
from window import MainWindow
from theme import apply_theme

if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    apply_theme(app)
    win = MainWindow()
    win.show()
    sys.exit(app.exec())
