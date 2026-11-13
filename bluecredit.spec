# PyInstaller spec: builds BlueCredit.app (macOS) or BlueCredit.exe (Windows)
import sys
a = Analysis(["run_bluecredit.py"], pathex=["."], datas=[("assets", "assets")],
             hiddenimports=["PySide6.QtPrintSupport", "keyring.backends"],
             excludes=["tkinter", "matplotlib", "IPython", "pytest", "scipy", "pandas", "numpy"])
pyz = PYZ(a.pure)
icon = "assets/icon.icns" if sys.platform == "darwin" else None
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="BlueCredit", console=False, icon=icon)
coll = COLLECT(exe, a.binaries, a.datas, name="BlueCredit")
if sys.platform == "darwin":
    app = BUNDLE(coll, name="BlueCredit.app", icon=icon, bundle_identifier="com.bluepeak.bluecredit",
                 info_plist={"CFBundleShortVersionString": "1.0.0", "NSHighResolutionCapable": True})
