# SUMA — File & Folder Locker (v2, multi-file)

**SUMA (Secure Utility Management App)** — a desktop file & folder locker for Windows.
Lock files and folders behind a master password with real encryption.

## Running (Windows)

1. Install Python 3.10+ from [python.org](https://www.python.org).
2. Open a terminal in this folder (right-click the folder → "Open in Terminal").
3. Install dependencies:

```
pip install PySide6 cryptography
```

4. Run the app:

```
python main.py
```

Always run `python main.py` **from this folder** — all files must live in the same folder.

## Tests

```
python test_suma.py
```

31 automated tests: password hashing (old + new format), file encryption
round-trip, decryption of legacy encrypted files, tamper detection, safe
lock/unlock, manifest backup/recovery, ZIP-slip protection, and legacy vault
migration.

## File map

| File            | Purpose |
|-----------------|---------|
| `main.py`       | Entry point: splash screen + app launch. That's it. |
| `config.py`     | All paths: config/vault under `%APPDATA%/SUMA`, legacy vault discovery and safe migration, profile picture |
| `crypto.py`     | Password hashing (PBKDF2 600k, auto-upgrade from legacy 200k), Fernet keys, chunked file encryption |
| `vault.py`      | VaultEngine: safe lock/unlock (temp file → verify → atomic save), manifest backup, ZIP-slip protection |
| `stego.py`      | Hiding / extracting the recovery key inside a picture (LSB steganography) |
| `utils.py`      | Small helpers: file-size formatting, password generator, file categories |
| `ui_widgets.py` | Small UI pieces: buttons, cards, avatar, sidebar, file rows |
| `screens.py`    | All screens: setup, unlock, dashboard, settings, recovery, etc. |
| `app.py`        | Title bar + MainWindow (navigation, tray, auto-lock, hotkey) |
| `test_suma.py`  | Automated tests |

Looking for something? The file name tells you where it lives — a crypto
issue is in `crypto.py`, a screen issue in `screens.py`.

## First run (migration)

If your old vault is in `D:/SUMA` or in this folder, the app finds it and
**copies** it to `%APPDATA%/SUMA` (the old data stays where it is — nothing is
deleted) and shows a message. Password, files and recovery stay exactly as they
were.

## Building the .exe (Windows)

```
pip install pyinstaller
pyinstaller --clean --onefile --windowed --name SUMA ^
  --icon assets\suma-icon.ico ^
  --add-data "assets;assets" ^
  --add-binary "<python-install>\abi3t-compat\python3t.dll;." ^
  main.py
```

The result lands in `dist\SUMA.exe` — no Python needed to run it.
(`python3t.dll` lives next to your Python install; without it the frozen app
cannot load `cryptography`.)
See `SUMA-Setup.iss` for building the Windows installer with Inno Setup.

## Important notes

- If you lose **both** your master password and your recovery picture, your data
  cannot be recovered. Keep your recovery picture safe.
- Traces of deleted files may remain on SSD/disk — SUMA does not claim to be a
  "secure delete" tool.
- Vault data lives in `%APPDATA%/SUMA/vault`.

© 2026 MRS KRYPTON — All Rights Reserved
