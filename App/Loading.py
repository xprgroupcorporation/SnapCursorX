import ctypes
import importlib
import importlib.util
import os
import random
import subprocess
import sys
import time

from pathlib import Path

if os.name == "nt":
    os.environ.setdefault("QT_ENABLE_HIGHDPI_SCALING", "0")
    os.environ.setdefault("QT_AUTO_SCREEN_SCALE_FACTOR", "0")
    os.environ.setdefault("QT_SCALE_FACTOR", "1")

from PySide6 import QtCore, QtGui, QtWidgets
from Core.Utils import ASSETS_DIR, CONFIG_DIR, CORE_DIR
from Core.info_loader import load_info_config


def build_startup_manifest():
    core_dir = CORE_DIR

    return {
        "python_dependencies": [
            {"name": "subprocess", "import_name": "subprocess"},
            {"name": "sys", "import_name": "sys"},
            {"name": "os", "import_name": "os"},
            {"name": "json", "import_name": "json"},
            {"name": "ctypes", "import_name": "ctypes"},
            {"name": "tempfile", "import_name": "tempfile"},
            {"name": "urllib.request", "import_name": "urllib.request"},
            {"name": "urllib.error", "import_name": "urllib.error"},
            {"name": "random", "import_name": "random"},
            {"name": "time", "import_name": "time"},
            {"name": "copy", "import_name": "copy"},
            {"name": "threading", "import_name": "threading"},
            {"name": "winsound", "import_name": "winsound"},
            {"name": "PySide6.QtWidgets", "import_name": "PySide6.QtWidgets", "package": "PySide6"},
            {"name": "PySide6.QtCore", "import_name": "PySide6.QtCore", "package": "PySide6"},
            {"name": "PySide6.QtGui", "import_name": "PySide6.QtGui", "package": "PySide6"},
            {"name": "PySide6.QtGui.QDesktopServices", "import_name": "PySide6.QtGui", "package": "PySide6"},
            {"name": "win32gui", "import_name": "win32gui", "package": "pywin32"},
            {"name": "win32con", "import_name": "win32con", "package": "pywin32"},
            {"name": "win32api", "import_name": "win32api", "package": "pywin32"},
            {"name": "pyautogui", "import_name": "pyautogui", "package": "pyautogui"},
            {"name": "pybind11", "import_name": "pybind11", "package": "pybind11", "optional": True},
        ],
        "native_components": [
            {
                "name": "ClickEngine",
                "type": "dll",
                "paths": [
                    str(core_dir / "ClickEngine_tuned.dll"),
                    str(core_dir / "ClickEngine.dll"),
                    str(core_dir / "ClickEngine_recovery.dll"),
                    str(core_dir / "ClickEngine_smoketest.dll"),
                ],
                "loader": "windll",
                "required": True,
                "python_preloads": ["pybind11"],
                "initialize": {
                    "exports": ["start_clicking", "stop_clicking", "set_callback"],
                },
            },
        ],
    }


_info_config = load_info_config(
    required=[
        "NAME",
        "VERSION",
        "COMPANY",
        "TAGLINE",
        "COPYRIGHT",
        "EMAIL",
    ]
)
_startup_manifest = build_startup_manifest()


def _configure_windows_dpi():
    if os.name != "nt":
        return
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
        return
    except Exception:
        pass
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass


class AppInfo:
    NAME = _info_config["NAME"]
    VERSION = _info_config["VERSION"]
    APP_FULL = f"{NAME} - {VERSION}"

    COMPANY = _info_config["COMPANY"]
    TAGLINE = _info_config["TAGLINE"]
    COPYRIGHT = _info_config["COPYRIGHT"]
    EMAIL = _info_config["EMAIL"]


class StartupWorker(QtCore.QObject):
    progress = QtCore.Signal(int, int, str)
    task_changed = QtCore.Signal(str)
    log = QtCore.Signal(str)
    finished = QtCore.Signal()
    failed = QtCore.Signal(str)

    def __init__(self, manifest: dict):
        super().__init__()
        self._manifest = manifest
        self._completed_steps = 0
        self._native_handles = []
        self._dll_directories = []
        self._random_min_delay = 0.03
        self._random_max_delay = 0.05

    @QtCore.Slot()
    def run(self):
        try:
            total_steps = len(self._manifest.get("python_dependencies", [])) + len(self._manifest.get("native_components", []))
            if total_steps <= 0:
                raise RuntimeError("Startup manifest contains no steps.")

            self.log.emit("Loader initialized.")
            self.log.emit("Starting unified startup verification...")

            self._run_python_stage(total_steps)
            self._run_native_stage(total_steps)

            self.finished.emit()
        except Exception as exc:
            message = str(exc).strip() or exc.__class__.__name__
            self.log.emit(f"ERROR: {message}")
            self.failed.emit(message)

    def _run_python_stage(self, total_steps: int):
        for item in self._manifest.get("python_dependencies", []):
            display_name = item.get("name") or item.get("package") or item.get("import_name")
            package_name = item.get("package")
            import_name = item.get("import_name", display_name)
            optional = bool(item.get("optional", False))

            self._set_task(total_steps, f"Checking Python: {display_name}")
            self.log.emit(f"Checking Python dependency: {display_name} ({import_name})")

            if self._can_import(import_name):
                self.log.emit(f"Python dependency ready: {display_name}")
                self._complete_step(total_steps, f"Checking Python: {display_name}")
                self._apply_random_delay()
                continue

            if optional:
                self.log.emit(f"Optional Python dependency missing: {display_name}")
                self._complete_step(total_steps, f"Checking Python: {display_name} (optional missing)")
                self._apply_random_delay()
                continue

            if not package_name:
                raise RuntimeError(f"Missing required Python dependency: {display_name}")

            self._set_task(total_steps, f"Installing Python: {display_name}")
            self.log.emit(f"Installing missing Python dependency: {package_name} for {display_name}")
            self._install_package(package_name)

            if not self._can_import(import_name):
                raise RuntimeError(f"Failed to import Python dependency after install: {display_name}")

            self.log.emit(f"Installed Python dependency: {display_name}")
            self._complete_step(total_steps, f"Installing Python: {display_name}")
            self._apply_random_delay()

    def _run_native_stage(self, total_steps: int):
        for item in self._manifest.get("native_components", []):
            name = item["name"]
            component_type = str(item.get("type", "")).lower()
            required = bool(item.get("required", True))
            component_path = self._resolve_native_component_path(item)

            if component_path is None:
                raw_paths = item.get("paths") or [item.get("path")]
                joined_paths = ", ".join(str(Path(path)) for path in raw_paths if path)
                if required:
                    raise RuntimeError(f"Missing required native component: {joined_paths}")
                self.log.emit(f"Optional native component missing: {joined_paths or name}")
                self._complete_step(total_steps, f"Loading Native: {name} (optional missing)")
                continue

            self._set_task(total_steps, f"Loading Native: {component_path.name}")
            self.log.emit(f"Verifying native component: {name} -> {component_path}")

            checksum = item.get("checksum")
            if checksum:
                self._validate_checksum(component_path, checksum)

            self._set_task(total_steps, f"Initializing Native: {component_path.name}")
            handle = self._load_native_component(item, component_type, component_path)
            self._native_handles.append(handle)

            self.log.emit(f"Native component ready: {name}")
            self._complete_step(total_steps, f"Initializing Native: {component_path.name}")

    def _resolve_native_component_path(self, item: dict):
        raw_paths = item.get("paths")
        if raw_paths:
            for raw_path in raw_paths:
                candidate = Path(raw_path)
                if candidate.exists():
                    return candidate
            return None

        raw_path = item.get("path")
        if not raw_path:
            return None
        return Path(raw_path)

    def _set_task(self, total_steps: int, prefix: str):
        current_index = min(self._completed_steps + 1, max(1, total_steps))
        self.task_changed.emit(f"{prefix} ({current_index}/{total_steps})")

    def _complete_step(self, total_steps: int, prefix: str):
        self._completed_steps += 1
        self.progress.emit(self._completed_steps, total_steps, f"{prefix} ({self._completed_steps}/{total_steps})")

    def _apply_random_delay(self):
        time.sleep(random.uniform(self._random_min_delay, self._random_max_delay))

    def _can_import(self, import_name: str) -> bool:
        try:
            importlib.import_module(import_name)
            return True
        except Exception:
            return False

    def _install_package(self, package_name: str):
        process = subprocess.Popen(
            [sys.executable, "-m", "pip", "install", package_name],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )

        if process.stdout:
            for line in process.stdout:
                line = line.strip()
                if line:
                    self.log.emit(line)

        return_code = process.wait()
        if return_code != 0:
            raise RuntimeError(f"pip install failed for {package_name} (exit code {return_code})")

    def _validate_checksum(self, component_path: Path, expected_checksum: str):
        import hashlib

        digest = hashlib.sha256(component_path.read_bytes()).hexdigest().lower()
        if digest != str(expected_checksum).lower():
            raise RuntimeError(f"Checksum mismatch for {component_path.name}")

    def _load_native_component(self, item: dict, component_type: str, component_path: Path):
        for module_name in item.get("python_preloads", []):
            try:
                importlib.import_module(module_name)
                self.log.emit(f"Python preload ready: {module_name}")
            except Exception as exc:
                self.log.emit(f"Python preload skipped: {module_name} ({exc})")

        if hasattr(os, "add_dll_directory"):
            dll_directory = os.add_dll_directory(str(component_path.parent))
            self._dll_directories.append(dll_directory)

        loader = str(item.get("loader", "")).lower()

        if component_type in ("dll", "exe") or loader == "windll":
            handle = ctypes.WinDLL(str(component_path))
        elif component_type == "pyd":
            module_name = item.get("module_name") or component_path.stem
            spec = importlib.util.spec_from_file_location(module_name, str(component_path))
            if spec is None or spec.loader is None:
                raise RuntimeError(f"Unable to create import spec for {component_path.name}")
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            handle = module
        else:
            raise RuntimeError(f"Unsupported native component type: {component_type or 'unknown'}")

        initialize = item.get("initialize", {})
        for export_name in initialize.get("exports", []):
            if not hasattr(handle, export_name):
                raise RuntimeError(f"{component_path.name} missing required export: {export_name}")

        return handle


class LoadingWindow(QtWidgets.QWidget):
    startup_ready = QtCore.Signal()

    def __init__(self, startup_delay_ms: int = 0):
        super().__init__()
        self._loaded_count = 0
        self._total_count = 0
        self._worker_thread = None
        self._worker = None
        self._loading_started = False
        self._failed = False

        self.setWindowTitle(f"{AppInfo.NAME} Loader")
        self.setFixedSize(660, 380)
        self.setWindowFlags(
            QtCore.Qt.Window
            | QtCore.Qt.FramelessWindowHint
            | QtCore.Qt.NoDropShadowWindowHint
            | QtCore.Qt.WindowStaysOnTopHint
        )
        self.setAttribute(QtCore.Qt.WA_TranslucentBackground)

        self._build_ui()
        self._center_on_screen()

        self._start_timer = QtCore.QTimer(self)
        self._start_timer.setSingleShot(True)
        self._start_timer.timeout.connect(self._start_loading)
        self._start_timer.start(max(0, int(startup_delay_ms)))

    def _build_ui(self):
        outer = QtWidgets.QVBoxLayout(self)
        outer.setContentsMargins(16, 16, 16, 16)

        card = QtWidgets.QFrame()
        card.setObjectName("card")
        card.setStyleSheet(
            """
            QFrame#card {
                background: transparent;
                border: 1px solid rgba(255,255,255,30);
                border-radius: 14px;
            }
            QLabel {
                color: white;
            }
            """
        )
        outer.addWidget(card)

        root = QtWidgets.QVBoxLayout(card)
        root.setContentsMargins(24, 20, 24, 20)
        root.setSpacing(0)

        top = QtWidgets.QHBoxLayout()
        top.setSpacing(18)
        root.addLayout(top)

        self.logo_label = QtWidgets.QLabel()
        self.logo_label.setFixedSize(110, 110)
        self.logo_label.setAlignment(QtCore.Qt.AlignCenter)
        self._set_logo()
        top.addWidget(self.logo_label)

        right = QtWidgets.QVBoxLayout()
        right.setSpacing(2)
        top.addLayout(right, 1)

        title = QtWidgets.QLabel(AppInfo.NAME)
        title.setFont(QtGui.QFont("Times New Roman", 28, QtGui.QFont.Bold))
        right.addWidget(title)
        right.addSpacing(4)

        version = QtWidgets.QLabel(AppInfo.VERSION)
        version.setFont(QtGui.QFont("Times New Roman", 14))
        version.setStyleSheet("color: rgba(255,255,255,180);")
        right.addWidget(version)
        right.addSpacing(8)

        credit = QtWidgets.QLabel(
            f"<b><span style='font-size:10pt;'>{AppInfo.COMPANY}</span></b><br>"
            f"<span style='font-size:8.9pt;'>{AppInfo.TAGLINE}</span><br>"
            f"<span style='font-size:6.9pt;'>{AppInfo.COPYRIGHT} - {AppInfo.EMAIL}</span>"
        )
        credit.setStyleSheet("color: rgba(255,255,255,140); font-family: Times New Roman;")
        right.addWidget(credit)

        root.addSpacing(10)

        self.log_view = QtWidgets.QPlainTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setFrameShape(QtWidgets.QFrame.NoFrame)
        self.log_view.setMaximumBlockCount(200)
        self.log_view.setStyleSheet(
            """
            QPlainTextEdit {
                background: rgba(0, 0, 0, 90);
                border: 1px solid rgba(255,255,255,32);
                border-radius: 10px;
                color: rgba(255,255,255,210);
                padding: 8px;
            }
            """
        )
        self.log_view.setFont(QtGui.QFont("Consolas", 9))
        self.log_view.setFixedHeight(100)
        root.addWidget(self.log_view)

        right.addStretch()
        root.addSpacing(5)

        status_row = QtWidgets.QHBoxLayout()
        status_row.setContentsMargins(2, 0, 2, 0)

        self.preparing_label = QtWidgets.QLabel("Preparing...")
        self.preparing_label.setStyleSheet("color: rgba(255,255,255,140);")

        self.status_label = QtWidgets.QLabel("Waiting")
        self.status_label.setAlignment(QtCore.Qt.AlignCenter)
        self.status_label.setStyleSheet("color: rgba(255,255,255,180);")

        self.progress_info = QtWidgets.QLabel("0/0 Steps - 0%")
        self.progress_info.setAlignment(QtCore.Qt.AlignRight)
        self.progress_info.setStyleSheet("color: rgba(255,255,255,150);")

        status_row.addWidget(self.preparing_label)
        status_row.addStretch()
        status_row.addWidget(self.status_label)
        status_row.addStretch()
        status_row.addWidget(self.progress_info)
        root.addLayout(status_row)

        root.addSpacing(6)

        self.progress_bar = QtWidgets.QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setFixedHeight(14)
        self.progress_bar.setStyleSheet(
            """
            QProgressBar {
                background: rgba(0, 0, 0, 75);
                border: 1px solid rgba(255,255,255,60);
                border-radius: 7px;
                padding: 1px;
            }
            QProgressBar::chunk {
                border-radius: 7px;
                background: qlineargradient(
                    x1:0, y1:0, x2:1, y2:0,
                    stop:0 #ff4b4b,
                    stop:0.5 #b03dff,
                    stop:1 #5f8dff
                );
            }
            """
        )
        root.addWidget(self.progress_bar)

        self._append_log("Loader initialized.")
        self._append_log("Waiting for startup verification...")

    def _set_logo(self):
        logo_path = ASSETS_DIR / "XPR_Developer_Network_Logo_Alt.png"
        pixmap = QtGui.QPixmap(str(logo_path))
        if pixmap.isNull():
            self.logo_label.setText("LOGO")
            return
        self.logo_label.setPixmap(
            pixmap.scaled(110, 110, QtCore.Qt.KeepAspectRatio, QtCore.Qt.SmoothTransformation)
        )

    def _center_on_screen(self):
        screen = QtWidgets.QApplication.primaryScreen()
        if screen:
            rect = screen.availableGeometry()
            self.move(
                rect.center().x() - self.width() // 2,
                rect.center().y() - self.height() // 2,
            )

    def _start_loading(self):
        if self._loading_started:
            return
        self._loading_started = True

        self.status_label.setText("Starting startup checks (1/1)")
        self._append_log("Starting unified Python/C++ native loading...")

        self._worker_thread = QtCore.QThread(self)
        self._worker = StartupWorker(_startup_manifest)
        self._worker.moveToThread(self._worker_thread)

        self._worker_thread.started.connect(self._worker.run)
        self._worker.progress.connect(self._on_progress)
        self._worker.task_changed.connect(self._on_task_changed)
        self._worker.log.connect(self._append_log)
        self._worker.finished.connect(self._on_finished)
        self._worker.failed.connect(self._on_failed)
        self._worker.finished.connect(self._worker_thread.quit)
        self._worker.failed.connect(self._worker_thread.quit)
        self._worker.finished.connect(self._worker.deleteLater)
        self._worker.failed.connect(self._worker.deleteLater)
        self._worker_thread.finished.connect(self._worker_thread.deleteLater)

        self._worker_thread.start()

    def _append_log(self, text: str):
        self.log_view.appendPlainText(text)
        self.log_view.verticalScrollBar().setValue(
            self.log_view.verticalScrollBar().maximum()
        )

    def _on_task_changed(self, label: str):
        self.status_label.setText(label)

    def _on_progress(self, loaded: int, total: int, label: str):
        self._loaded_count = loaded
        self._total_count = total
        progress = 0 if total == 0 else int((loaded / total) * 100)

        self.preparing_label.setText("Preparing..." if loaded < total else "Complete")
        self.status_label.setText(label)
        self.progress_info.setText(f"{loaded}/{total} Steps - {progress}%")
        self.progress_bar.setValue(progress)

    def _on_finished(self):
        if self._failed:
            return
        self.preparing_label.setText("Complete")
        self.status_label.setText("Startup Ready")
        self.progress_info.setText(f"{self._total_count}/{self._total_count} Steps - 100%")
        self.progress_bar.setValue(100)
        self._append_log("All Python and native startup checks completed.")
        self.startup_ready.emit()

    def _on_failed(self, message: str):
        self._failed = True
        self.preparing_label.setText("Failed")
        self.status_label.setText("Startup Failed")
        self.progress_bar.setStyleSheet(
            """
            QProgressBar {
                background: rgba(0, 0, 0, 75);
                border: 1px solid rgba(255,120,120,90);
                border-radius: 7px;
                padding: 1px;
            }
            QProgressBar::chunk {
                border-radius: 7px;
                background: #ff4b4b;
            }
            """
        )
        progress = 0 if self._total_count == 0 else int((self._loaded_count / self._total_count) * 100)
        self.progress_info.setText(f"{self._loaded_count}/{self._total_count} Steps - {progress}%")
        self._append_log(f"Startup failed: {message}")

    def paintEvent(self, event):
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.Antialiasing)

        rect = self.rect().adjusted(0, 0, -1, -1)

        gradient = QtGui.QLinearGradient(0, 0, self.width(), self.height())
        gradient.setColorAt(0, QtGui.QColor("#0f0c29"))
        gradient.setColorAt(0.45, QtGui.QColor("#400071"))
        gradient.setColorAt(1, QtGui.QColor("#24243e"))

        painter.setPen(QtCore.Qt.NoPen)
        painter.setBrush(gradient)
        painter.drawRoundedRect(rect, 16, 16)


def main():
    _configure_windows_dpi()
    app = QtWidgets.QApplication(sys.argv)

    icon_path = ASSETS_DIR / "app_icon.ico"
    if icon_path.exists():
        app.setWindowIcon(QtGui.QIcon(str(icon_path)))

    window = LoadingWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
