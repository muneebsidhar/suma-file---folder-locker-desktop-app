# SUMA — File & Folder Locker (v2, multi-file)

## Run karne ka tareeqa (Windows)

1. Python 3.10+ install karo (python.org se).
2. Is folder mein terminal kholo (folder mein right-click → "Open in Terminal").
3. Dependencies install karo:

```
pip install PySide6 cryptography
```

4. App chalao:

```
python main.py
```

Hamesha **isi folder se** `python main.py` chalao — saari files ek hi folder mein
honi chahiye.

## Tests

```
python test_suma.py
```

31 automated tests: password hashing (purana + naya format), file encryption
round-trip, purani encrypted files ka decrypt, tamper detection, safe lock/unlock,
manifest backup/recovery, ZIP-slip protection, aur legacy vault migration.

## Files ka hisab

| File            | Kaam |
|-----------------|------|
| `main.py`       | Entry point: splash screen + app launch. Bas! |
| `config.py`     | Saare raste (paths): `%APPDATA%/SUMA` mein config/vault, purane vault ki talaash aur safe migration, profile picture |
| `crypto.py`     | Password hashing (PBKDF2 600k, purane 200k se auto-upgrade), Fernet keys, tukron wali file encryption |
| `vault.py`      | VaultEngine: safe lock/unlock (temp file → verify → atomic save), manifest backup, ZIP-slip se hifazat |
| `stego.py`      | Recovery key ko tasveer mein chhupana / nikalna |
| `utils.py`      | Chhote helpers: file size format, password generator, file categories |
| `ui_widgets.py` | Chhote UI tukre: buttons, cards, avatar, sidebar, file rows |
| `screens.py`    | Saari screens: setup, unlock, dashboard, settings, recovery waghera |
| `app.py`        | Title bar + MainWindow (navigation, tray, auto-lock, hotkey) |
| `test_suma.py`  | Automated tests |

Kuch dhoondhna ho to file ke naam se pata chal jata hai — crypto ka masla
`crypto.py` mein, screen ka masla `screens.py` mein.

## Pehli baar chalane pe (migration)

Agar tumhara purana vault `D:/SUMA` ya usi folder mein hai to app usay khud
dhoondh kar `%APPDATA%/SUMA` mein **copy** kar legi (purana data wahin rahega,
delete nahi hoga) aur ek message dikhayegi. Password, files aur recovery
sab waise ke waise.

## Zaroori baatein

- Master password + recovery tasveer **dono** gum ho jayein to data wapas
  nahi aa sakta. Recovery tasveer sambhal kar rakho.
- SSD/disk par delete ki hui file ke nishan baqi reh sakte hain — SUMA
  "secure delete" ka daawa nahi karta.
- Vault ka data `%APPDATA%/SUMA/vault` mein rehta hai.
