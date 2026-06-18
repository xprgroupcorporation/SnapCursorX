from __future__ import annotations

import argparse
import os
import platform
import struct
import subprocess
import sys
import tempfile
from pathlib import Path


CORE_DIR = Path(__file__).resolve().parent
CPP_FILE = CORE_DIR / "ClickEngine.cpp"
DEFAULT_DLL = CORE_DIR / "ClickEngine.dll"
DEFAULT_VSDEVCMD = Path(r"C:\Program Files\Microsoft Visual Studio\18\Community\Common7\Tools\VsDevCmd.bat")
EXTRA_VARIANTS = (
    "ClickEngine_dynamic.dll",
    "ClickEngine_dynamic.exp",
    "ClickEngine_dynamic.lib",
)


def detect_architecture() -> str:
    return "amd64" if struct.calcsize("P") * 8 == 64 else "x86"


def preflight_check(vsdevcmd: Path, output_name: str) -> tuple[bool, list[str]]:
    issues: list[str] = []

    if platform.system() != "Windows":
        issues.append("This helper only supports Windows.")
    if not CPP_FILE.exists():
        issues.append(f"Missing source file: {CPP_FILE}")
    if not vsdevcmd.exists():
        issues.append(f"Missing VsDevCmd.bat: {vsdevcmd}")

    output_path = CORE_DIR / output_name
    try:
        CORE_DIR.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile("w", dir=str(CORE_DIR), delete=True, encoding="utf-8") as handle:
            handle.write("ok")
    except OSError as exc:
        issues.append(f"Core directory is not writable: {exc}")

    if output_path.exists():
        try:
            temp_path = output_path.with_suffix(output_path.suffix + ".writecheck")
            with temp_path.open("wb") as handle:
                handle.write(b"ok")
            temp_path.unlink()
        except OSError:
            issues.append(
                f"Output folder is writable, but '{output_path.name}' may be locked by a running app."
            )

    return (len(issues) == 0, issues)


def find_vsdevcmd(explicit: str | None) -> Path:
    candidates: list[Path] = []
    if explicit:
        candidates.append(Path(explicit))
    env_path = os.environ.get("VSDEVCMD_PATH")
    if env_path:
        candidates.append(Path(env_path))
    candidates.append(DEFAULT_VSDEVCMD)

    for candidate in candidates:
        if candidate.exists():
            return candidate

    raise FileNotFoundError(
        "Could not find VsDevCmd.bat. Pass --vsdevcmd or set VSDEVCMD_PATH."
    )


def build_command(vsdevcmd: Path, arch: str, output_name: str) -> str:
    return "\n".join(
        [
            "@echo off",
            f'call "{vsdevcmd}" -arch={arch}',
            "if errorlevel 1 exit /b %errorlevel%",
            f'cl /nologo /DCLICKENGINE_EXPORTS /LD /EHsc "{CPP_FILE.name}" /Fe:{output_name} winmm.lib user32.lib ntdll.lib',
        ]
    )


def run_build(vsdevcmd: Path, arch: str, output_name: str) -> subprocess.CompletedProcess[str]:
    script_text = build_command(vsdevcmd, arch, output_name)
    temp_script: Path | None = None
    try:
        with tempfile.NamedTemporaryFile("w", suffix=".cmd", delete=False, encoding="utf-8") as handle:
            handle.write(script_text)
            temp_script = Path(handle.name)
        return subprocess.run(
            ["cmd", "/c", str(temp_script)],
            cwd=str(CORE_DIR),
            text=True,
            capture_output=True,
            check=False,
        )
    finally:
        if temp_script is not None:
            try:
                temp_script.unlink()
            except OSError:
                pass


def prune_variants() -> tuple[list[str], list[str]]:
    removed: list[str] = []
    locked: list[str] = []
    for name in EXTRA_VARIANTS:
        path = CORE_DIR / name
        if not path.exists():
            continue
        try:
            path.unlink()
            removed.append(name)
        except OSError:
            locked.append(name)
    return removed, locked


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build ClickEngine.dll from ClickEngine.cpp using MSVC."
    )
    parser.add_argument(
        "--vsdevcmd",
        help="Full path to VsDevCmd.bat. Defaults to Visual Studio 2026 Community path.",
    )
    parser.add_argument(
        "--arch",
        choices=("amd64", "x86", "auto"),
        default="auto",
        help="Build architecture. Defaults to current Python bitness.",
    )
    parser.add_argument(
        "--output",
        default=DEFAULT_DLL.name,
        help="Output DLL filename. Defaults to ClickEngine.dll.",
    )
    parser.add_argument(
        "--prune-old",
        action="store_true",
        help="Delete old temporary ClickEngine variants after a successful build.",
    )
    args = parser.parse_args()

    if not CPP_FILE.exists():
        print(f"Missing source file: {CPP_FILE}", file=sys.stderr)
        return 1

    try:
        vsdevcmd = find_vsdevcmd(args.vsdevcmd)
    except FileNotFoundError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    arch = detect_architecture() if args.arch == "auto" else args.arch
    print(f"[Py_C_dll_linker] Core dir: {CORE_DIR}")
    print(f"[Py_C_dll_linker] Using VsDevCmd: {vsdevcmd}")
    print(f"[Py_C_dll_linker] Target arch: {arch}")
    print(f"[Py_C_dll_linker] Output: {args.output}")

    ok, issues = preflight_check(vsdevcmd, args.output)
    if not ok:
        for issue in issues:
            print(f"[Py_C_dll_linker] Preflight: {issue}", file=sys.stderr)
        print("[Py_C_dll_linker] Exiting safely without changing anything.", file=sys.stderr)
        return 0

    result = run_build(vsdevcmd, arch, args.output)
    if result.stdout:
        print(result.stdout.rstrip())
    if result.stderr:
        print(result.stderr.rstrip(), file=sys.stderr)

    if result.returncode != 0:
        print(
            "[Py_C_dll_linker] Build failed. If ClickEngine.dll is locked, close the app and try again.",
            file=sys.stderr,
        )
        return result.returncode

    output_path = CORE_DIR / args.output
    if not output_path.exists():
        print(f"[Py_C_dll_linker] Build reported success but file is missing: {output_path}", file=sys.stderr)
        return 1

    print(f"[Py_C_dll_linker] Build succeeded: {output_path}")

    if args.prune_old:
        removed, locked = prune_variants()
        if removed:
            print(f"[Py_C_dll_linker] Removed: {', '.join(removed)}")
        if locked:
            print(f"[Py_C_dll_linker] Locked, could not remove: {', '.join(locked)}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
