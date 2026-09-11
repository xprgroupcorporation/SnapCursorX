from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from pprint import pformat


ROOT_DIR = Path(__file__).resolve().parents[2]
APP_DIR = ROOT_DIR / "App"
CORE_DIR = APP_DIR / "Core"
ENTRY_FILE = APP_DIR / "Main.py"
ICON_FILE = ROOT_DIR / "Assets" / "app_icon.ico"
ASSETS_DIR = ROOT_DIR / "Assets"
INFO_FILE = ROOT_DIR / "Data" / "Config" / "Info.json"
SOURCE_DATA_DIR = ROOT_DIR / "Data"
BUILD_INFO_FILE = CORE_DIR / "build_info.py"

BUILD_DIR = ROOT_DIR / "build"
PYINSTALLER_CACHE_DIR = ROOT_DIR / ".pyinstaller"
DIST_DIR = ROOT_DIR / "dist"
OUTPUT_DIR = ROOT_DIR / "__EXE_Build_Output"
OUTPUT_DATA_DIR = OUTPUT_DIR / "Data"
TEMP_DOCS_DIR = BUILD_DIR / "_export_docs"

EXCLUDED_MODULES = [
    "PyQt5",
    "numpy",
    "matplotlib",
    "pandas",
    "scipy",
    "tkinter",
    "cv2",
    "debugpy",
    "PySide6.QtPdf",
    "PySide6.QtQml",
    "PySide6.QtQuick",
    "PySide6.QtVirtualKeyboard",
]

DOC_FILES = [
    "LICENSE.txt",
    "README.md",
    "requirements.txt",
]


def load_info() -> dict:
    if not INFO_FILE.exists():
        raise FileNotFoundError(
            f"Info.json not found at expected path: {INFO_FILE}\n"
            "Make sure Data/Config/Info.json exists before building."
        )
    with INFO_FILE.open(encoding="utf-8") as handle:
        return json.load(handle)


def parse_numeric_version(raw: str) -> str:
    match = re.search(r"\d+(?:\.\d+)+", raw)
    return match.group(0) if match else "0.0.0"


def write_build_info_module(info: dict) -> Path:
    BUILD_INFO_FILE.parent.mkdir(parents=True, exist_ok=True)
    content = "BUILD_INFO = " + pformat(info, sort_dicts=False, width=120) + "\n"
    BUILD_INFO_FILE.write_text(content, encoding="utf-8")
    return BUILD_INFO_FILE


def is_production_compress_enabled(info: dict) -> bool:
    return bool(info.get("Production_Compress", False))


def is_example_setup_file(path: Path) -> bool:
    stem = path.stem.strip().lower().replace("_", " ")
    return stem.startswith("example")


def is_loadable_setup_file(path: Path) -> bool:
    if path.suffix.lower() != ".json":
        return False
    try:
        with path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return False
    return (
        isinstance(data, dict)
        and data.get("mode") in ("single", "sandbox")
        and bool(str(data.get("name", "")).strip())
    )


def should_publish_setup_file(path: Path, production_compress: bool) -> bool:
    if not production_compress:
        return True
    if is_example_setup_file(path):
        return True
    try:
        with path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return False
    setup_name = str(data.get("name", "")).strip()
    return setup_name.lower().startswith("example")


def ensure_entry_exists() -> None:
    if not ENTRY_FILE.exists():
        raise FileNotFoundError(f"Entry file not found: {ENTRY_FILE}")


def ensure_pyinstaller() -> None:
    try:
        __import__("PyInstaller")
    except ImportError as exc:
        raise RuntimeError(
            "PyInstaller is not installed for this Python environment.\n"
            f'Install it with: "{sys.executable}" -m pip install pyinstaller'
        ) from exc


def reset_build_workspace(exe_name: str) -> None:
    removed: list[Path] = []

    for path in (
        BUILD_DIR,
        PYINSTALLER_CACHE_DIR,
        DIST_DIR,
        OUTPUT_DIR,
        ROOT_DIR / f"{exe_name}.spec",
    ):
        if not path.exists():
            continue
        try:
            if path.is_dir():
                shutil.rmtree(path)
            else:
                path.unlink()
            removed.append(path)
        except OSError as exc:
            print(f"  [warn] Could not remove {path}: {exc}")

    if removed:
        print("Cleaned previous build output:")
        for path in removed:
            print(f"  - {path}")
    else:
        print("No previous build output found.")


def _write_version_file(info: dict, numeric_version: str, exe_name: str, copyright_: str) -> str:
    BUILD_DIR.mkdir(parents=True, exist_ok=True)
    version_file = BUILD_DIR / "version_info.txt"

    parts = [int(x) for x in numeric_version.split(".")]
    while len(parts) < 4:
        parts.append(0)
    ver_tuple = tuple(parts[:4])
    ver_str = ".".join(str(part) for part in ver_tuple)

    app_name = info.get("NAME", exe_name)
    company = info.get("COMPANY", "XPR Group Corporation")
    copyright_text = info.get("COPYRIGHT", copyright_)
    raw_ver = info.get("VERSION", numeric_version)

    content = f"""\
VSVersionInfo(
  ffi=FixedFileInfo(
    filevers={ver_tuple},
    prodvers={ver_tuple},
    mask=0x3f,
    flags=0x0,
    OS=0x40004,
    fileType=0x1,
    subtype=0x0,
    date=(0, 0),
  ),
  kids=[
    StringFileInfo([
      StringTable(
        u'040904B0',
        [StringStruct(u'CompanyName',      u'{company}'),
         StringStruct(u'FileDescription',  u'{app_name}'),
         StringStruct(u'FileVersion',      u'{ver_str}'),
         StringStruct(u'InternalName',     u'{exe_name}'),
         StringStruct(u'LegalCopyright',   u'{copyright_text} {company}'),
         StringStruct(u'OriginalFilename', u'{exe_name}.exe'),
         StringStruct(u'ProductName',      u'{app_name}'),
         StringStruct(u'ProductVersion',   u'{raw_ver}'),
        ])
    ]),
    VarFileInfo([VarStruct(u'Translation', [1033, 1200])])
  ]
)
"""
    version_file.write_text(content, encoding="utf-8")
    return str(version_file)


def _write_manifest_file(info: dict, exe_name: str) -> str:
    BUILD_DIR.mkdir(parents=True, exist_ok=True)
    manifest_file = BUILD_DIR / "manifest.xml"
    
    app_name = info.get("NAME", exe_name)
    company = info.get("COMPANY", "XPR Group Corporation")
    
    content = f"""\
<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<assembly xmlns="urn:schemas-microsoft-com:asm.v1" manifestVersion="1.0">
  <assemblyIdentity
    version="1.0.0.0"
    processorArchitecture="amd64"
    name="{company}.{app_name}"
    type="win32"
  />
  <description>{app_name}</description>
  
  <trustInfo xmlns="urn:schemas-microsoft-com:compatibility.v1">
    <security>
      <requestedPrivileges>
        <requestedExecutionLevel level="asInvoker" uiAccess="false"/>
      </requestedPrivileges>
    </security>
  </trustInfo>
  
  <asmv3:application xmlns:asmv3="urn:schemas-microsoft-com:asm.v3">
    <asmv3:windowsSettings xmlns="http://schemas.microsoft.com/SMI/2005/WindowsSettings">
      <dpiAware>true</dpiAware>
    </asmv3:windowsSettings>
  </asmv3:application>
  
  <compatibility xmlns="urn:schemas-microsoft-com:compatibility.v1">
    <application>
      <supportedOS Id="{{35138b9a-5d96-4fbd-8e2d-a2440225f93a}}"/>
      <supportedOS Id="{{4a2f28e3-53b9-4441-ba9c-d69d4a4a6e38}}"/>
      <supportedOS Id="{{1f676c76-80e1-4239-95bb-830fdb30664e}}"/>
      <supportedOS Id="{{8e0f7a12-bfb3-4fe8-b9a5-48fd50a15a9a}}"/>
      <supportedOS Id="{{35138b9a-5d96-4fbd-8e2d-a2440225f93a}}"/>
    </application>
  </compatibility>
</assembly>
"""
    manifest_file.write_text(content, encoding="utf-8")
    return str(manifest_file)


def _add_data_arg(command: list[str], source: Path, target: str) -> None:
    command.extend(["--add-data", f"{source}{os.pathsep}{target}"])


def build_exe(exe_name: str, version_file_path: str, manifest_file_path: str) -> Path:
    command = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--onedir",
        "--windowed",
        "--contents-directory",
        "_internal",
        "--name",
        exe_name,
        "--distpath",
        str(DIST_DIR),
        "--workpath",
        str(BUILD_DIR),
        "--specpath",
        str(ROOT_DIR),
        "--paths",
        str(APP_DIR),
        "--hidden-import",
        "Core.build_info",
        "--version-file",
        version_file_path,
        "--manifest",
        manifest_file_path,
    ]

    for module_name in EXCLUDED_MODULES:
        command.extend(["--exclude-module", module_name])

    if ICON_FILE.exists():
        command.extend(["--icon", str(ICON_FILE)])

    _add_data_arg(command, ASSETS_DIR, "Assets")
    _add_data_arg(command, SOURCE_DATA_DIR, "Data")

    for dll_path in sorted(CORE_DIR.glob("ClickEngine*.dll")):
        _add_data_arg(command, dll_path, "App/Core")

    command.append(str(ENTRY_FILE))
    subprocess.run(command, check=True, cwd=ROOT_DIR)

    exe_dir = DIST_DIR / exe_name
    if not exe_dir.exists():
        raise RuntimeError(f"PyInstaller completed but output folder was not found: {exe_dir}")
    return exe_dir


def copy_publish_docs() -> None:
    TEMP_DOCS_DIR.mkdir(parents=True, exist_ok=True)
    copied: list[str] = []

    for filename in DOC_FILES:
        source = ROOT_DIR / filename
        if not source.exists():
            continue
        target = OUTPUT_DIR / source.name
        shutil.copy2(source, target)
        copied.append(source.name)

    if copied:
        print("Copied publish docs:")
        for name in copied:
            print(f"  - {name}")


def copy_publish_data(production_compress: bool) -> None:
    if OUTPUT_DATA_DIR.exists():
        shutil.rmtree(OUTPUT_DATA_DIR)

    filtered_setups: list[str] = []
    removed_setups: list[str] = []

    def ignore_data_items(source_dir: str, names: list[str]) -> set[str]:
        source_path = Path(source_dir)
        ignored: set[str] = set()
        is_setups_dir = source_path.resolve() == (SOURCE_DATA_DIR / "Setups").resolve()
        is_data_root = source_path.resolve() == SOURCE_DATA_DIR.resolve()

        if not production_compress:
            return ignored

        for name in names:
            item_path = source_path / name
            if is_setups_dir and item_path.is_file() and item_path.suffix.lower() == ".json":
                if should_publish_setup_file(item_path, production_compress):
                    filtered_setups.append(str(item_path.relative_to(SOURCE_DATA_DIR)))
                else:
                    ignored.add(name)
                    removed_setups.append(str(item_path.relative_to(SOURCE_DATA_DIR)))
                continue

            if is_data_root and item_path.is_file() and is_loadable_setup_file(item_path):
                if should_publish_setup_file(item_path, production_compress):
                    filtered_setups.append(str(item_path.relative_to(SOURCE_DATA_DIR)))
                else:
                    ignored.add(name)
                    removed_setups.append(str(item_path.relative_to(SOURCE_DATA_DIR)))

        return ignored

    shutil.copytree(SOURCE_DATA_DIR, OUTPUT_DATA_DIR, ignore=ignore_data_items)

    if production_compress:
        print("Production_Compress enabled: only Example* setup files were published.")
        if filtered_setups:
            print("Published setup files:")
            for name in sorted(set(filtered_setups)):
                print(f"  - {name}")
        else:
            print("Published setup files: none")
        if removed_setups:
            print("Excluded private setup files:")
            for name in sorted(set(removed_setups)):
                print(f"  - {name}")
    else:
        print("Production_Compress disabled: copied all Data files for dev testing.")


def stage_publish_output(exe_dir: Path, production_compress: bool) -> Path:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    for item in exe_dir.iterdir():
        target = OUTPUT_DIR / item.name
        if target.exists():
            if target.is_dir():
                shutil.rmtree(target)
            else:
                target.unlink()
        if item.is_dir():
            shutil.copytree(item, target)
        else:
            shutil.copy2(item, target)

    copy_publish_data(production_compress)

    copy_publish_docs()
    return OUTPUT_DIR / f"{exe_dir.name}.exe"


def main() -> int:
    info = load_info()
    base_name = info.get("NAME", "SnapCursorX")
    raw_version = info.get("VERSION", "0.0.0")
    production_compress = is_production_compress_enabled(info)
    numeric_version = parse_numeric_version(raw_version)
    copyright_ = info.get("COPYRIGHT", "2026")

    exe_name = f"{base_name}_SE"

    print("=" * 56)
    print(f"  {base_name} | {raw_version}")
    print("=" * 56)
    print(f"  Info      : {INFO_FILE}")
    print(f"  Entry     : {ENTRY_FILE}")
    print(f"  PublishTo : {OUTPUT_DIR}")
    print(f"  Production_Compress: {production_compress}")
    print()

    ensure_entry_exists()
    ensure_pyinstaller()
    reset_build_workspace(exe_name)

    build_info_module = write_build_info_module(info)
    version_file_path = _write_version_file(info, numeric_version, exe_name, copyright_)
    manifest_file_path = _write_manifest_file(info, exe_name)

    print(f"  BuildInfo : {build_info_module}")
    print()
    print(f"Building portable package: {exe_name}")

    exe_dir = build_exe(exe_name, version_file_path, manifest_file_path)
    staged_exe = stage_publish_output(exe_dir, production_compress)

    if not staged_exe.exists():
        raise RuntimeError(f"Build completed but runnable exe was not staged: {staged_exe}")

    size_mb = staged_exe.stat().st_size / (1024 * 1024)
    print()
    print("Publish output ready:")
    print(f"  Exe  : {staged_exe}")
    print(f"  Data : {OUTPUT_DATA_DIR}")
    print(f"  Docs : {OUTPUT_DIR}")
    print(f"  Size : {size_mb:.1f} MB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
