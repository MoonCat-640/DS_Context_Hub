"""Build the self-contained Windows folder, offline installer and portable ZIP."""

import argparse
import hashlib
import importlib.metadata
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

VERSION = "0.1.1"
ROOT = Path(__file__).resolve().parent.parent
BUILD = ROOT / "build" / "windows"
BUNDLE = ROOT / "dist" / "ds_context_hub"
RELEASE = ROOT / "release"


def run(*args):
    subprocess.run([str(arg) for arg in args], cwd=ROOT, check=True)


def nsis_quote(value):
    return str(value).replace("$", "$$").replace('"', '$\\"')


def add_notices():
    notices = BUNDLE / "licenses"
    notices.mkdir(exist_ok=True)
    inventory = []
    for distribution in sorted(importlib.metadata.distributions(), key=lambda item: item.metadata["Name"].lower()):
        name = distribution.metadata["Name"]
        copied = []
        for file in distribution.files or []:
            if any(word in file.name.upper() for word in ("LICENSE", "LICENCE", "COPYING", "NOTICE")):
                source = Path(distribution.locate_file(file))
                if not source.is_file():
                    continue
                destination = notices / name / Path(*file.parts)
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source, destination)
                copied.append(str(destination.relative_to(BUNDLE)))
        inventory.append({"name": name, "version": distribution.version, "licenses": copied})
    for candidate in (Path(sys.base_prefix) / "LICENSE.txt", Path(sys.base_prefix) / "LICENSE"):
        if candidate.is_file():
            shutil.copyfile(candidate, notices / "Python-LICENSE.txt")
            break
    shutil.copytree(ROOT / "packaging" / "licenses", notices / "Qt", dirs_exist_ok=True)
    (notices / "packages.json").write_text(json.dumps(inventory, indent=2), encoding="utf-8")
    (BUNDLE / "THIRD_PARTY_NOTICES.txt").write_text(
        "DS Context Hub includes Python, Qt for Python (PySide6), cryptography and provider SDKs.\n"
        "The licenses directory contains the bundled distributions' license notices and version inventory.\n"
        "Qt and PySide6 are distributed as replaceable shared libraries under their included open-source licenses.\n"
        "Qt for Python 6.9.2 source: https://download.qt.io/official_releases/QtForPython/pyside6/PySide6-6.9.2-src/\n"
        "Qt 6.9.2 source: https://download.qt.io/archive/qt/6.9/6.9.2/single/\n"
        "Application source: https://github.com/MoonCat-640/DS_Context_Hub\n",
        encoding="utf-8",
    )


def generate_payload():
    files = sorted(path for path in BUNDLE.rglob("*") if path.is_file())
    install, uninstall = [], []
    previous = None
    for path in files:
        relative = path.relative_to(BUNDLE)
        parent = str(relative.parent)
        if parent != previous:
            suffix = "" if parent == "." else "\\" + nsis_quote(parent)
            install.append(f'SetOutPath "$INSTDIR{suffix}"')
            previous = parent
        install.append(f'File "{nsis_quote(path)}"')
        uninstall.append(f'Delete "$INSTDIR\\{nsis_quote(relative)}"')
    directories = sorted((path for path in BUNDLE.rglob("*") if path.is_dir()), key=lambda item: len(item.parts), reverse=True)
    uninstall.extend(f'RMDir "$INSTDIR\\{nsis_quote(path.relative_to(BUNDLE))}"' for path in directories)
    (BUILD / "payload-install.nsh").write_text("\n".join(install) + "\n", encoding="utf-8-sig")
    (BUILD / "payload-uninstall.nsh").write_text("\n".join(uninstall) + "\n", encoding="utf-8-sig")
    return sum(path.stat().st_size for path in files) // 1024 + 1


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--nsis", type=Path, required=True, help="Path to the NSIS makensis.exe compiler")
    parser.add_argument("--skip-freeze", action="store_true", help="Reuse a previously built and verified folder")
    args = parser.parse_args()
    if sys.platform != "win32" or sys.maxsize <= 2**32:
        parser.error("Build on 64-bit Windows with 64-bit Python")
    if not args.nsis.is_file():
        parser.error("The specified NSIS compiler does not exist")
    for directory in (BUNDLE, BUILD, RELEASE):
        if not directory.resolve().is_relative_to(ROOT):
            parser.error(f"Build output must be inside the project: {directory}")
    BUILD.mkdir(parents=True, exist_ok=True)
    RELEASE.mkdir(exist_ok=True)
    if not args.skip_freeze:
        os.environ["PYINSTALLER_CONFIG_DIR"] = str(BUILD / "cache")
        run(sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", ROOT / "packaging" / "ds_context_hub.spec")
    shutil.copyfile(ROOT / "LICENSE", BUNDLE / "LICENSE.txt")
    shutil.copyfile(ROOT / "README.md", BUNDLE / "README.md")
    add_notices()
    report = BUILD / "frozen-self-test.json"
    environment = os.environ.copy()
    for name in ("PYTHONHOME", "PYTHONPATH", "QT_PLUGIN_PATH", "QT_QPA_PLATFORM_PLUGIN_PATH", "QT_QPA_PLATFORM"):
        environment.pop(name, None)
    environment["PATH"] = os.pathsep.join([str(Path(os.environ["WINDIR"]) / "System32"), os.environ["WINDIR"]])
    result = subprocess.run([str(BUNDLE / "ds_context_hub.exe"), "--self-test", str(report)], cwd=BUILD, env=environment, timeout=120)
    if result.returncode != 0 or not json.loads(report.read_text(encoding="utf-8"))["ok"]:
        raise RuntimeError(f"Frozen application verification failed. Inspect {report}")
    size = generate_payload()
    compiler = Path(os.environ["WINDIR"]) / "Microsoft.NET" / "Framework64" / "v4.0.30319" / "csc.exe"
    run(compiler, "/nologo", "/target:winexe", "/platform:x64", "/optimize+",
        f"/out:{BUILD / 'PathEntry.exe'}", ROOT / "packaging" / "PathEntry.cs")
    run(args.nsis.resolve(), "/V3", "/INPUTCHARSET", "UTF8", f"/DVERSION={VERSION}", f"/DPROJECT_ROOT={ROOT}",
        f"/DGENERATED_DIR={BUILD}", f"/DOUTPUT_DIR={RELEASE}", f"/DINSTALLED_KB={size}",
        ROOT / "packaging" / "installer.nsi")
    portable = RELEASE / f"DS_Context_Hub-{VERSION}-windows-x64.zip"
    with ZipFile(portable, "w", ZIP_DEFLATED) as zipped:
        for path in sorted(BUNDLE.rglob("*")):
            if path.is_file():
                zipped.write(path, path.relative_to(BUNDLE.parent))
    checksums = []
    for path in (RELEASE / "Setup.exe", portable):
        with path.open("rb") as artifact:
            checksum = hashlib.file_digest(artifact, "sha256").hexdigest()
        checksums.append(f"{checksum}  {path.name}")
    (RELEASE / "SHA256SUMS.txt").write_text("\n".join(checksums) + "\n", encoding="ascii")
    print("Release assets are ready in", RELEASE)


if __name__ == "__main__":
    main()
