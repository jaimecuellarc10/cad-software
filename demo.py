"""
Standalone demo — run this to see the properties panel in action.

    pip install PySide6 qtawesome
    python demo.py

Includes a small toolbar to switch between selection states so you can verify
the no-selection view, single-object view, and multi-selection *VARIES* behavior.
"""

import sys

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QApplication, QDockWidget, QHBoxLayout, QLabel, QMainWindow,
    QPushButton, QStatusBar, QWidget,
)

from theme import apply_theme
from widgets.properties_panel import PropertiesPanel


# Fake CAD entities for demo. Replace with your real entity model.
SAMPLE_LINE_1 = {
    "type": "Line",
    "properties": {
        "color": "ByLayer",
        "layer": "0",
        "linetype": "ByLayer",
        "start_x": 0.0, "start_y": 0.0,
        "end_x": 100.0, "end_y": 50.0,
        "length": 111.803,
    },
}
SAMPLE_LINE_2 = {
    "type": "Line",
    "properties": {
        "color": QColor("#FF0000"),
        "layer": "Walls",
        "linetype": "ByLayer",
        "start_x": 0.0, "start_y": 0.0,
        "end_x": 200.0, "end_y": 0.0,
        "length": 200.0,
    },
}
SAMPLE_CIRCLE = {
    "type": "Circle",
    "properties": {
        "color": "ByLayer",
        "layer": "Hidden",
        "linetype": "Dashed",
        "center_x": 50.0, "center_y": 50.0,
        "radius": 25.0,
    },
}


class DemoMainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("CAD UI Starter — Properties Panel Demo")
        self.resize(1100, 700)

        # Fake canvas in the center
        canvas = QLabel("(drawing canvas placeholder)")
        canvas.setAlignment(Qt.AlignCenter)
        canvas.setStyleSheet("background-color: #1F1F1F; color: #555;")
        self.setCentralWidget(canvas)

        # Properties panel in a dock
        self.props = PropertiesPanel()
        self.props.propertyChanged.connect(self._on_property_changed)

        dock = QDockWidget("Properties", self)
        dock.setWidget(self.props)
        dock.setMinimumWidth(300)
        self.addDockWidget(Qt.RightDockWidgetArea, dock)

        # Demo toolbar to switch selection states
        self._build_demo_toolbar()

        # Status bar
        self.setStatusBar(QStatusBar())
        self.statusBar().showMessage("Ready")

    def _build_demo_toolbar(self):
        bar = QWidget()
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(8, 4, 8, 4)

        for label, sel in [
            ("No selection", []),
            ("Single Line",  [SAMPLE_LINE_1]),
            ("Two Lines (varies)", [SAMPLE_LINE_1, SAMPLE_LINE_2]),
            ("Mixed (Line + Circle)", [SAMPLE_LINE_1, SAMPLE_CIRCLE]),
        ]:
            btn = QPushButton(label)
            btn.clicked.connect(lambda _=False, s=sel: self.props.set_selection(s))
            layout.addWidget(btn)
        layout.addStretch(1)

        dock = QDockWidget("Demo Controls", self)
        dock.setWidget(bar)
        self.addDockWidget(Qt.TopDockWidgetArea, dock)

    def _on_property_changed(self, name: str, value):
        self.statusBar().showMessage(f"Property changed: {name} = {value}", 3000)


def main():
    app = QApplication(sys.argv)
    apply_theme(app)
    win = DemoMainWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
