# build_windows.py 交给 PyInstaller 的构建描述，SPECPATH 由 PyInstaller 注入。
from pathlib import Path
from PyInstaller.utils.hooks import collect_submodules, copy_metadata

root = Path(SPECPATH).parent
icon = root / "assets" / "ds-context-hub.ico"
# EXE 内嵌资源供资源管理器使用，同一 ICO 作为数据文件供 Qt 和安装快捷方式使用。
datas = [(str(icon), "assets")]
# SDK 会在运行时查询已安装的版本和依赖信息，需将这些包的元数据一并带上。
for package in ("openai", "anthropic", "google-genai", "cryptography", "PySide6-Essentials"):
    datas += copy_metadata(package, recursive=True)

# 静态导入分析看不到 SDK 动态加载的模块，hiddenimports 将它们显式纳入。
a = Analysis(
    [str(root / "packaging" / "launcher.py")],
    pathex=[str(root), str(root / "packaging")],
    datas=datas,
    hiddenimports=collect_submodules("google.genai") + collect_submodules("opentelemetry"),
    excludes=["tkinter", "PyQt5", "PyQt6", "PySide2"],
    noarchive=False,
)
# Python 模块进入 PYZ，原生 DLL 和 Qt 插件由最后的 COLLECT 放到 exe 旁边。
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, [], exclude_binaries=True,
    name="ds_context_hub", debug=False, strip=False, upx=False,
    console=False, disable_windowed_traceback=False,
    icon=str(icon),
    version=str(root / "packaging" / "version_info.txt"),
)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="ds_context_hub")
