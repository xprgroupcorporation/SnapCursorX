from PySide6 import QtWidgets, QtCore, QtGui

from Config.Manager import AppConfig
from Core.Utils import ASSETS_DIR
from UI.components.animations import WindowAnimator


def _event_global_pos(event):
    if hasattr(event, "globalPosition"):
        return event.globalPosition().toPoint()
    return event.globalPos()


class TitleBar(QtWidgets.QWidget):
    def __init__(self, parent=None, title_text=None, is_sub_window=False):
        super().__init__(parent)
        self.parent = parent
        self.setFixedHeight(40)
        self.setStyleSheet("background: transparent; color: white;")

        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(10, 0, 10, 0)

        self.logo = QtWidgets.QLabel(self)
        logo_path = ASSETS_DIR / "XPR_Developer_Network_Logo_Alt.png"
        pixmap = QtGui.QPixmap(str(logo_path))
        pixmap = pixmap.scaled(40, 40, QtCore.Qt.KeepAspectRatio, QtCore.Qt.SmoothTransformation)
        self.logo.setPixmap(pixmap)
        self.logo.setFixedSize(40, 40)
        layout.addWidget(self.logo)

        self.title = QtWidgets.QLabel(title_text or AppConfig.NAME, self)
        font = QtGui.QFont("Times New Roman", 16)
        font.setBold(True)
        self.title.setFont(font)
        layout.addWidget(self.title)
        layout.addStretch()

        self.min_btn = QtWidgets.QPushButton("–", self)
        self.min_btn.setFont(QtGui.QFont("Times New Roman", 8))
        self.close_btn = QtWidgets.QPushButton("X", self)
        self.close_btn.setFont(QtGui.QFont("Times New Roman", 8))

        for btn in (self.min_btn, self.close_btn):
            btn.setFixedSize(30, 30)
            btn.setStyleSheet("""
                QPushButton {
                    background: transparent;
                    color: white;
                    border: none;
                }
                QPushButton:hover {
                    background: rgba(255,255,255,60);
                    border-radius: 4px;
                }
            """)

        self.min_btn.clicked.connect(lambda: WindowAnimator.minimize(self.parent))
        if is_sub_window:
            self.close_btn.setText("Return")
            self.close_btn.setFixedSize(60, 30)
            self.close_btn.setFont(QtGui.QFont("Times New Roman", 10))
            self.close_btn.clicked.connect(self.parent.close)
        else:
            self.close_btn.setText("X")
            if hasattr(self.parent, "close_all"):
                self.close_btn.clicked.connect(self.parent.close_all)
            else:
                self.close_btn.clicked.connect(self.parent.close)

        layout.addWidget(self.min_btn)
        layout.addWidget(self.close_btn)

        self.drag_pos = None

    def mousePressEvent(self, event):
        if event.button() == QtCore.Qt.LeftButton:
            target = self.childAt(event.pos())
            if target not in (self.min_btn, self.close_btn):
                self.drag_pos = _event_global_pos(event)

    def mouseMoveEvent(self, event):
        if event.buttons() == QtCore.Qt.LeftButton and self.drag_pos:
            self.parent.move(
                self.parent.pos() + _event_global_pos(event) - self.drag_pos
            )
            self.drag_pos = _event_global_pos(event)

    def mouseReleaseEvent(self, event):
        self.drag_pos = None
