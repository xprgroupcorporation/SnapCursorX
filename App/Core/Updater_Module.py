import json
import re
import tempfile
import urllib.error
import urllib.request
from pathlib import Path

from PySide6 import QtCore


def parse_numeric_version_text(raw_version: str) -> str:
    match = re.search(r"\d+(?:\.\d+)+", str(raw_version or ""))
    return match.group(0) if match else "0.0.0"


def compare_versions(left: str, right: str) -> int:
    def normalize(version_text: str):
        parts = [int(part) for part in str(version_text).split(".") if str(part).isdigit()]
        while len(parts) < 4:
            parts.append(0)
        return parts[:4]

    left_parts = normalize(left)
    right_parts = normalize(right)
    if left_parts > right_parts:
        return 1
    if left_parts < right_parts:
        return -1
    return 0


class UpdateCheckWorker(QtCore.QObject):
    finished = QtCore.Signal(dict)

    def __init__(self, current_version: str, release_api_url: str, release_page_url: str, request_id: int = 0):
        super().__init__()
        self._current_version = parse_numeric_version_text(current_version)
        self._release_api_url = str(release_api_url or "").strip()
        self._release_page_url = str(release_page_url or "").strip()
        self._request_id = int(request_id)

    def run(self):
        try:
            if not self._has_internet():
                self.finished.emit(self._failure_result())
                return

            release_data = self._load_release_data()
            if not release_data:
                self.finished.emit(self._failure_result())
                return

            latest_version = self._resolve_latest_version(release_data)
            assets = self._extract_assets(release_data.get("assets", []))
            release_page_url = str(
                release_data.get("html_url")
                or release_data.get("url")
                or self._release_page_url
            )

            if latest_version and compare_versions(latest_version, self._current_version) > 0:
                self.finished.emit({
                    "request_id": self._request_id,
                    "status": "update_available",
                    "label": f"New Update!\nVer{latest_version}",
                    "latest_version": latest_version,
                    "release_page_url": release_page_url,
                    "assets": assets,
                })
                return

            self.finished.emit({
                "request_id": self._request_id,
                "status": "latest",
                "label": "(Latest ver)",
                "latest_version": latest_version or self._current_version,
                "release_page_url": release_page_url,
                "assets": assets,
            })
        except Exception as exc:
            self.finished.emit(self._failure_result(str(exc).strip() or exc.__class__.__name__))

    def _failure_result(self, detail: str = "") -> dict:
        label = "Check your connection and try again."
        if detail:
            label = f"{label} ({detail})"
        return {
            "request_id": self._request_id,
            "status": "check_failed",
            "label": label,
            "error": detail,
            "latest_version": self._current_version,
            "release_page_url": self._release_page_url,
            "assets": {},
        }

    def _has_internet(self) -> bool:
        try:
            request = urllib.request.Request(
                "https://api.github.com",
                headers={"User-Agent": "SnapCursorX-UpdateChecker"},
            )
            with urllib.request.urlopen(request, timeout=4):
                return True
        except Exception:
            return False

    def _load_release_data(self):
        if not self._release_api_url:
            return None
        url = self._release_api_url
        try:
            data = self._request_json(url)
            if isinstance(data, list):
                return data[0] if data else None
            return data
        except urllib.error.HTTPError as exc:
            if exc.code == 404 and url.rstrip("/").endswith("/releases/latest"):
                releases_url = url.rstrip("/")[:-len("/latest")]
                releases = self._request_json(releases_url)
                if isinstance(releases, list) and releases:
                    return releases[0]
            raise RuntimeError(f"GitHub API returned {exc.code}") from exc
        except Exception as exc:
            raise RuntimeError(str(exc).strip() or exc.__class__.__name__) from exc

    def _request_json(self, url: str):
        request = urllib.request.Request(
            url,
            headers={
                "Accept": "application/vnd.github+json",
                "User-Agent": "SnapCursorX-UpdateChecker",
            },
        )
        with urllib.request.urlopen(request, timeout=6) as response:
            return json.loads(response.read().decode("utf-8"))

    def _extract_assets(self, assets: list[dict]):
        result = {}
        for asset in assets:
            name = str(asset.get("name", ""))
            url = str(asset.get("browser_download_url", ""))
            lowered = name.lower()
            if not name or not url:
                continue
            if "installer" in lowered or lowered.endswith(".msi") or lowered.endswith("setup.exe"):
                result.setdefault("installer", {"name": name, "url": url})
                continue
            if lowered.endswith(".zip"):
                result.setdefault("portable", {"name": name, "url": url})
                continue
            if lowered.endswith(".exe"):
                result.setdefault("portable", {"name": name, "url": url})
        return result

    def _resolve_latest_version(self, release_data: dict) -> str:
        candidates = [
            release_data.get("tag_name", ""),
            release_data.get("name", ""),
        ]
        for asset in release_data.get("assets", []):
            candidates.append(asset.get("name", ""))

        for candidate in candidates:
            parsed = parse_numeric_version_text(candidate)
            if parsed != "0.0.0":
                return parsed
        return "0.0.0"


class UpdateDownloadWorker(QtCore.QObject):
    progress = QtCore.Signal(int)
    finished = QtCore.Signal(str)
    failed = QtCore.Signal(str)

    def __init__(self, download_url: str, filename: str, target_dir: str | None = None):
        super().__init__()
        self._download_url = str(download_url or "")
        self._filename = str(filename or "SnapCursorX_Update.exe")
        self._target_dir = str(target_dir or "").strip()

    def run(self):
        try:
            if self._target_dir:
                download_dir = Path(self._target_dir)
            else:
                download_dir = Path(tempfile.gettempdir()) / "SnapCursorX_Updates"
            download_dir.mkdir(parents=True, exist_ok=True)
            target_path = download_dir / self._filename

            request = urllib.request.Request(
                self._download_url,
                headers={"User-Agent": "SnapCursorX-Updater"},
            )
            with urllib.request.urlopen(request, timeout=30) as response:
                total_size = int(response.headers.get("Content-Length", "0") or "0")
                downloaded = 0
                with target_path.open("wb") as handle:
                    while True:
                        chunk = response.read(1024 * 128)
                        if not chunk:
                            break
                        handle.write(chunk)
                        downloaded += len(chunk)
                        if total_size > 0:
                            percent = max(0, min(100, int(downloaded * 100 / total_size)))
                            self.progress.emit(percent)

            self.progress.emit(100)
            self.finished.emit(str(target_path))
        except Exception as exc:
            self.failed.emit(str(exc).strip() or exc.__class__.__name__)
