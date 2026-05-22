from PySide6 import QtWidgets, QtCore, QtGui


class FileMenuPopup(QtWidgets.QWidget):
    def __init__(self, parent_setup_ui):
        super().__init__(parent_setup_ui, QtCore.Qt.Popup | QtCore.Qt.FramelessWindowHint)
        self.setup_ui = parent_setup_ui
        self.setAttribute(QtCore.Qt.WA_TranslucentBackground)
        self.setAttribute(QtCore.Qt.WA_DeleteOnClose, False)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(2)

        def make_item(text, callback, is_divider=False):
            if is_divider:
                line = QtWidgets.QFrame()
                line.setFrameShape(QtWidgets.QFrame.HLine)
                line.setStyleSheet("color: rgba(255,255,255,40);")
                return line
            btn = QtWidgets.QPushButton(text)
            btn.setFixedHeight(18)
            btn.setFont(QtGui.QFont("Times New Roman", 8))
            btn.setCursor(QtCore.Qt.PointingHandCursor)
            btn.setStyleSheet("""
                QPushButton {
                    background: transparent;
                    color: white;
                    border: none;
                    text-align: left;
                    padding-left: 6px;
                    padding-right: 6px;
                }
                QPushButton:hover {
                    background: rgba(255,255,255,50);
                    border-radius: 4px;
                }
            """)
            btn.clicked.connect(callback)
            btn.clicked.connect(self.hide)
            return btn

        layout.addWidget(make_item("Save", self._on_save))
        layout.addWidget(make_item("Quit Setup", self._on_quit))
        layout.addWidget(make_item("", None, is_divider=True))
        layout.addWidget(make_item("Settings", self._on_settings))
        layout.addWidget(make_item("Credits", self._on_credits))
        layout.addWidget(make_item("", None, is_divider=True))
        layout.addWidget(make_item("Shutdown", self._on_shutdown))

        self.setFixedWidth(110)
        self.adjustSize()

    def _get_control_panel(self):
        """Walk up to find the ControlPanel parent."""
        app = QtWidgets.QApplication.instance()
        for widget in app.topLevelWidgets():
            if hasattr(widget, 'show_active_setup') and hasattr(widget, 'show_settings') and hasattr(widget, 'show_credits'):
                return widget
        return None

    def _on_save(self):
        self.setup_ui.save()

    def _on_quit(self):
        self._restore_cp()
        self.setup_ui.close()

    def _on_shutdown(self):
        if not self.setup_ui.prompt_save_before_close():
            return
        cp = self._get_control_panel()
        if cp and hasattr(cp, "close_all"):
            cp.close_all()
        else:
            QtWidgets.QApplication.quit()

    def _restore_cp(self):
        """Restore ControlPanel if it is minimized."""
        cp = self._get_control_panel()
        if cp:
            if cp.isMinimized():
                cp.setWindowState(QtCore.Qt.WindowNoState)
                cp.show()
                cp.raise_()
                cp.activateWindow()

    def _on_settings(self):
        cp = self._get_control_panel()
        if cp:
            self._restore_cp()

            cp._from_setup = True  # 🔥 KEY FIX

            center = cp.geometry().center()
            cp.resize(580, 360)
            rect = cp.geometry()
            rect.moveCenter(center)
            cp.move(rect.topLeft())

            cp.show()
            cp.raise_()
            cp.activateWindow()
            cp.show_settings()

    def _on_credits(self):
        cp = self._get_control_panel()
        if cp:
            self._restore_cp()

            cp._from_setup = True  # 🔥 KEY FIX

            center = cp.geometry().center()
            cp.resize(580, 360)
            rect = cp.geometry()
            rect.moveCenter(center)
            cp.move(rect.topLeft())

            cp.show()
            cp.raise_()
            cp.activateWindow()
            cp.show_credits()

    def paintEvent(self, event):
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.Antialiasing)
        painter.setBrush(QtGui.QColor(30, 20, 55, 230))
        painter.setPen(QtGui.QPen(QtGui.QColor(255, 255, 255, 40), 1))
        painter.drawRoundedRect(self.rect().adjusted(1, 1, -1, -1), 6, 6)
