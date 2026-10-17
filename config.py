import os
import sys
import json
import shutil


def _base_data_dir():
    if os.name == "nt":
        root = os.environ.get("APPDATA") or os.path.expanduser("~")
    else:
        root = os.environ.get("XDG_DATA_HOME") or os.path.join(
            os.path.expanduser("~"), ".local", "share")
    return os.path.join(root, "SUMA")


DATA_DIR = _base_data_dir()
CONFIG_PATH = os.path.join(DATA_DIR, "suma_config.json")
VAULT_DIR = os.path.join(DATA_DIR, "vault")
PROFILE_PATH = os.path.join(DATA_DIR, "profile.png")
BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def _legacy_config_candidates():
    cands = []
    for base in (os.getcwd(), BASE_DIR, "D:/SUMA", "D:\\SUMA"):
        cands.append(os.path.join(base, "suma_config.json"))
        cands.append(os.path.join(base, "suma_config", "suma_config.json"))
    seen = set()
    out = []
    for c in cands:
        if c not in seen:
            seen.add(c)
            out.append(c)
    return out


def _legacy_vault_for(cfg_path):
    tried = [
        os.path.join(os.path.dirname(cfg_path), "vault"),
        os.path.join(BASE_DIR, "vault"),
        os.path.join(os.getcwd(), "vault"),
        "D:/SUMA/vault",
        "D:\\SUMA\\vault",
    ]
    for v in tried:
        mf = os.path.join(v, "manifest.json")
        if os.path.isdir(v) and (os.path.isfile(mf) or
                                 any(f.endswith(".suma") for f in os.listdir(v))):
            return v
    return None


def _read_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def migrate_legacy(legacy_cfg, legacy_vault):
    os.makedirs(VAULT_DIR, exist_ok=True)
    shutil.copy2(legacy_cfg, CONFIG_PATH)
    if legacy_vault:
        for fn in os.listdir(legacy_vault):
            s = os.path.join(legacy_vault, fn)
            d = os.path.join(VAULT_DIR, fn)
            if os.path.isfile(s) and not os.path.isfile(d):
                shutil.copy2(s, d)
    for pp in (os.path.join(BASE_DIR, "profile.png"),
               os.path.join(os.getcwd(), "profile.png")):
        if os.path.isfile(pp) and not os.path.isfile(PROFILE_PATH):
            shutil.copy2(pp, PROFILE_PATH)
            break
    cfg = _read_json(CONFIG_PATH)
    mf = os.path.join(VAULT_DIR, "manifest.json")
    if os.path.isfile(mf):
        m = _read_json(mf)
        if not isinstance(m, list):
            raise ValueError("legacy manifest is not a list")
    return cfg


def startup_config():
    if os.path.isfile(CONFIG_PATH):
        try:
            return CONFIG_PATH, _read_json(CONFIG_PATH), False
        except Exception:
            return CONFIG_PATH, None, False
    for cand in _legacy_config_candidates():
        if os.path.isfile(cand):
            try:
                _read_json(cand)
            except Exception:
                continue
            cfg = migrate_legacy(cand, _legacy_vault_for(cand))
            return CONFIG_PATH, cfg, True
    return None, None, False


def find_config():
    if os.path.isfile(CONFIG_PATH):
        try:
            return CONFIG_PATH, _read_json(CONFIG_PATH)
        except Exception:
            return CONFIG_PATH, None
    return None, None


def save_config(data):
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def save_config_to(path, data):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def save_profile_pic(src):
    from PySide6.QtGui import QPixmap
    from PySide6.QtCore import Qt
    pm = QPixmap(src)
    if pm.isNull():
        raise ValueError("Could not read that image.")
    pm = pm.scaled(256, 256, Qt.KeepAspectRatio, Qt.SmoothTransformation)
    os.makedirs(DATA_DIR, exist_ok=True)
    if not pm.save(PROFILE_PATH, "PNG"):
        raise IOError("Could not save profile picture.")


def load_avatar_pm():
    from PySide6.QtGui import QPixmap
    pm = QPixmap()
    if os.path.isfile(PROFILE_PATH):
        pm = QPixmap(PROFILE_PATH)
        if not pm.isNull():
            s = min(pm.width(), pm.height())
            pm = pm.copy((pm.width() - s) // 2, (pm.height() - s) // 2, s, s)
    return pm


def profile_path():
    return PROFILE_PATH
