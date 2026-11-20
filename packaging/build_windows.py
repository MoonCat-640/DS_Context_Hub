"""将桌面应用冻结为独立目录，自检通过后，用同一份文件制作离线安装包和便携 ZIP。"""

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
# BUILD 存放中间产物，BUNDLE 是可以直接运行的完整目录，RELEASE 存放供下载的文件。
BUILD = ROOT / "build" / "windows"
BUNDLE = ROOT / "dist" / "ds_context_hub"
RELEASE = ROOT / "release"


def run(*args):
    """从仓库根目录运行构建工具，任何非零退出码都会终止这次构建。"""
    subprocess.run([str(arg) for arg in args], cwd=ROOT, check=True)


def nsis_quote(value):
    """转义 NSIS 字符串中的美元符号和双引号，使真实文件名可直接写入脚本。"""
    return str(value).replace("$", "$$").replace('"', '$\\"')


def add_notices():
    """从构建环境收集包版本和许可证，并补入解释器与 Qt 的许可文本。"""
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
                # 不同库常用同一个 LICENSE 文件名。按发行包名和原相对路径分开存放。
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
    """按 BUNDLE 内容生成一对 NSIS 安装、卸载清单，并以 KiB 返回预计安装大小。"""
    files = sorted(path for path in BUNDLE.rglob("*") if path.is_file())
    install, uninstall = [], []
    previous = None
    for path in files:
        relative = path.relative_to(BUNDLE)
        parent = str(relative.parent)
        if parent != previous:
            # NSIS 的 File 指令写入当前 SetOutPath，切换子目录时必须同步切换目标。
            suffix = "" if parent == "." else "\\" + nsis_quote(parent)
            install.append(f'SetOutPath "$INSTDIR{suffix}"')
            previous = parent
        install.append(f'File "{nsis_quote(path)}"')
        uninstall.append(f'Delete "$INSTDIR\\{nsis_quote(relative)}"')
    # 删完已安装文件后，从最深的目录向上尝试删除空目录，用户另外放入的文件会保留。
    directories = sorted((path for path in BUNDLE.rglob("*") if path.is_dir()), key=lambda item: len(item.parts), reverse=True)
    uninstall.extend(f'RMDir "$INSTDIR\\{nsis_quote(path.relative_to(BUNDLE))}"' for path in directories)
    (BUILD / "payload-install.nsh").write_text("\n".join(install) + "\n", encoding="utf-8-sig")
    (BUILD / "payload-uninstall.nsh").write_text("\n".join(uninstall) + "\n", encoding="utf-8-sig")
    return sum(path.stat().st_size for path in files) // 1024 + 1


def main():
    """解析构建参数，完成冻结、自检、安装器编译和发行文件校验。"""
    parser = argparse.ArgumentParser()
    parser.add_argument("--nsis", type=Path, required=True, help="Path to the NSIS makensis.exe compiler")
    parser.add_argument("--skip-freeze", action="store_true", help="Reuse a previously built and verified folder")
    args = parser.parse_args()
    if sys.platform != "win32" or sys.maxsize <= 2**32:
        parser.error("Build on 64-bit Windows with 64-bit Python")
    if not args.nsis.is_file():
        parser.error("The specified NSIS compiler does not exist")
    # PyInstaller 的 --clean 和 --noconfirm 会清理旧产物，先确认实际输出位置位于仓库内。
    for directory in (BUNDLE, BUILD, RELEASE):
        if not directory.resolve().is_relative_to(ROOT):
            parser.error(f"Build output must be inside the project: {directory}")
    BUILD.mkdir(parents=True, exist_ok=True)
    RELEASE.mkdir(exist_ok=True)
    if not args.skip_freeze:
        # 使用当前虚拟环境的 Python，确保冻结的 SDK、Qt 插件与构建用的版本一致。
        os.environ["PYINSTALLER_CONFIG_DIR"] = str(BUILD / "cache")
        run(sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", ROOT / "packaging" / "ds_context_hub.spec")
    shutil.copyfile(ROOT / "LICENSE", BUNDLE / "LICENSE.txt")
    shutil.copyfile(ROOT / "README.md", BUNDLE / "README.md")
    add_notices()
    report = BUILD / "frozen-self-test.json"
    # 用精简的子进程环境运行真正的 exe，防止开发机上的 Python 或 Qt 插件掩盖漏打包的问题。
    environment = os.environ.copy()
    for name in ("PYTHONHOME", "PYTHONPATH", "QT_PLUGIN_PATH", "QT_QPA_PLATFORM_PLUGIN_PATH", "QT_QPA_PLATFORM"):
        environment.pop(name, None)
    environment["PATH"] = os.pathsep.join([str(Path(os.environ["WINDIR"]) / "System32"), os.environ["WINDIR"]])
    result = subprocess.run([str(BUNDLE / "ds_context_hub.exe"), "--self-test", str(report)], cwd=BUILD, env=environment, timeout=120)
    if result.returncode != 0 or not json.loads(report.read_text(encoding="utf-8"))["ok"]:
        raise RuntimeError(f"Frozen application verification failed. Inspect {report}")
    size = generate_payload()
    # PATH 助手单独编译后嵌入安装器和卸载器，两者都能独立维护注册表中的完整 PATH。
    compiler = Path(os.environ["WINDIR"]) / "Microsoft.NET" / "Framework64" / "v4.0.30319" / "csc.exe"
    run(compiler, "/nologo", "/target:winexe", "/platform:x64", "/optimize+",
        f"/out:{BUILD / 'PathEntry.exe'}", ROOT / "packaging" / "PathEntry.cs")
    run(args.nsis.resolve(), "/V3", "/INPUTCHARSET", "UTF8", f"/DVERSION={VERSION}", f"/DPROJECT_ROOT={ROOT}",
        f"/DGENERATED_DIR={BUILD}", f"/DOUTPUT_DIR={RELEASE}", f"/DINSTALLED_KB={size}",
        ROOT / "packaging" / "installer.nsi")
    portable = RELEASE / f"DS_Context_Hub-{VERSION}-windows-x64.zip"
    # ZIP 保留顶层 ds_context_hub 及其内部层级，解压后 exe 才能找到旁边的 _internal。
    with ZipFile(portable, "w", ZIP_DEFLATED) as zipped:
        for path in sorted(BUNDLE.rglob("*")):
            if path.is_file():
                zipped.write(path, path.relative_to(BUNDLE.parent))
    checksums = []
    # 对最终供下载的两个文件逐一计算散列，改名不会改变对应的 SHA-256。
    for path in (RELEASE / "Setup.exe", portable):
        with path.open("rb") as artifact:
            checksum = hashlib.file_digest(artifact, "sha256").hexdigest()
        checksums.append(f"{checksum}  {path.name}")
    (RELEASE / "SHA256SUMS.txt").write_text("\n".join(checksums) + "\n", encoding="ascii")
    print("Release assets are ready in", RELEASE)


if __name__ == "__main__":
    main()
