from PySide6 import QtCore, QtWidgets


class HorizontalStepSpinBox(QtWidgets.QSpinBox):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setButtonSymbols(QtWidgets.QAbstractSpinBox.NoButtons)
        self._button_layout = "horizontal"

        self._up_btn = QtWidgets.QPushButton("\u25b4", self)
        self._down_btn = QtWidgets.QPushButton("\u25be", self)

        btn_style = """
            QPushButton {
                background: transparent;
                color: rgba(255,255,255,170);
                border: none;
                padding: 0px;
                text-align: center;
                font: bold 13pt 'Consolas';
            }
            QPushButton:hover {
                color: rgba(255,255,255,235);
            }
            QPushButton:pressed {
                color: rgba(255,255,255,255);
            }
            QPushButton:disabled {
                color: rgba(255,255,255,70);
            }
        """
        self._up_btn.setStyleSheet(btn_style)
        self._down_btn.setStyleSheet(btn_style)
        self._up_btn.setCursor(QtCore.Qt.PointingHandCursor)
        self._down_btn.setCursor(QtCore.Qt.PointingHandCursor)
        self._up_btn.setFixedWidth(16)
        self._down_btn.setFixedWidth(16)
        self._up_btn.clicked.connect(lambda: self.stepBy(1))
        self._down_btn.clicked.connect(lambda: self.stepBy(-1))

        if self.lineEdit() is not None:
            self.lineEdit().setTextMargins(0, 0, 26, 0)
            self.lineEdit().setAlignment(QtCore.Qt.AlignVCenter | QtCore.Qt.AlignLeft)

    def set_button_layout(self, layout: str):
        normalized = str(layout or "horizontal").strip().lower()
        self._button_layout = "vertical" if normalized == "vertical" else "horizontal"
        self.updateGeometry()
        self.update()

    def setButtonLayout(self, layout: str):
        self.set_button_layout(layout)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        height = self.height()
        right_pad = 4

        if self._button_layout == "vertical":
            btn_w = 12
            gap = 1
            total_h = max(16, height - 6)
            btn_h = max(8, (total_h - gap) // 2)
            x = self.width() - right_pad - btn_w
            y = max(0, (height - ((btn_h * 2) + gap)) // 2)
            self._up_btn.setGeometry(x, y, btn_w, btn_h)
            self._down_btn.setGeometry(x, y + btn_h + gap, btn_w, btn_h)
            if self.lineEdit() is not None:
                self.lineEdit().setTextMargins(0, 0, btn_w + right_pad + 2, 0)
            return

        btn_w = 12
        gap = 2
        btn_h = max(14, height - 6)
        y = max(0, (height - btn_h) // 2)
        down_x = self.width() - right_pad - btn_w
        up_x = down_x - gap - btn_w
        self._up_btn.setGeometry(up_x, y, btn_w, btn_h)
        self._down_btn.setGeometry(down_x, y, btn_w, btn_h)
        if self.lineEdit() is not None:
            self.lineEdit().setTextMargins(0, 0, (btn_w * 2) + gap + right_pad + 2, 0)
