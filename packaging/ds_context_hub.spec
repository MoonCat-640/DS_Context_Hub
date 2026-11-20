# Build with the dedicated environment described in packaging/README.md.
from pathlib import Path
from PyInstaller.utils.hooks import collect_submodules, copy_metadata

root = Path(SPECPATH).parent
datas = []
for package in ("openai", "anthropic", "google-genai", "cryptography", "PySide6-Essentials"):
    datas += copy_metadata(package, recursive=True)

a = Analysis(
    [str(root / "packaging" / "launcher.py")],
    pathex=[str(root), str(root / "packaging")],
    datas=datas,
    hiddenimports=collect_submodules("google.genai") + collect_submodules("opentelemetry"),
    excludes=["tkinter", "PyQt5", "PyQt6", "PySide2"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, [], exclude_binaries=True,
    name="ds_context_hub", debug=False, strip=False, upx=False,
    console=False, disable_windowed_traceback=False,
    version=str(root / "packaging" / "version_info.txt"),
)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="ds_context_hub")
