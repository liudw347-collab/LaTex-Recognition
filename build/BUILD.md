# Build instructions — Windows exe packaging

This script uses PyInstaller to bundle the TextLens app + all dependencies +
Python interpreter into a single distributable folder (or .exe).

## Prerequisites

1. Install Python 3.10+ from https://www.python.org/downloads/
2. Open PowerShell in this folder
3. Create a venv and install dependencies:

   ```powershell
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1
   pip install -r requirements.txt
   pip install pyinstaller==6.10.0
   ```

## Build

Double-click `build_exe.bat`, or in the activated venv run:

```powershell
pyinstaller textlens.spec --clean --noconfirm
```

The packaged app will appear in `dist\TextLens\`.
Distribute the whole `TextLens\` folder to users.

## Single-file mode (optional)

For a single self-extracting .exe, replace `textlens.spec` build with:

```powershell
pyinstaller --onefile --windowed --name TextLens --add-data "src;src" main.py
```

Note: onefile mode has slower startup (~3-5s to extract) but is easier to
distribute. The default folder mode (textlens.spec) starts in <1s.
