import os
import json
import shutil
import zipfile
import tempfile
import secrets
from datetime import datetime

import config
import utils
from crypto import encrypt_file, decrypt_file


class ManifestCorruptError(Exception):
    pass


class ActivityLog:
    def __init__(self, path=None):
        self.path = path or os.path.join(config.VAULT_DIR, "activity.json")
        self.items = self._load()

    def _load(self):
        try:
            if os.path.isfile(self.path):
                with open(self.path, "r", encoding="utf-8") as f:
                    return json.load(f)
        except Exception:
            pass
        return []

    def _save(self):
        os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
        tmp = self.path + ".tmp"
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self.items[-500:], f, indent=2)
            os.replace(tmp, self.path)
        except Exception:
            if os.path.isfile(tmp):
                os.remove(tmp)

    def add(self, action, detail=""):
        self.items.append({
            "at": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "action": action,
            "detail": detail,
        })
        self._save()

    def clear(self):
        self.items = []
        self._save()


def zip_dir_to_temp(src_dir):
    fd, tmp = tempfile.mkstemp(suffix=".zip")
    os.close(fd)
    try:
        with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as z:
            for root, dirs, files in os.walk(src_dir):
                for d in dirs:
                    full = os.path.join(root, d)
                    if not os.listdir(full):
                        z.writestr(os.path.relpath(full, src_dir) + "/", "")
                for fn in files:
                    full = os.path.join(root, fn)
                    z.write(full, os.path.relpath(full, src_dir))
        return tmp
    except Exception:
        if os.path.isfile(tmp):
            os.remove(tmp)
        raise


def safe_extract(zip_path, dest):
    dest_abs = os.path.abspath(dest)
    with zipfile.ZipFile(zip_path, "r") as z:
        for m in z.infolist():
            target = os.path.abspath(os.path.join(dest_abs, m.filename))
            if target != dest_abs and not target.startswith(dest_abs + os.sep):
                raise ValueError(f"blocked unsafe archive entry: {m.filename!r}")
        z.extractall(dest_abs)


def _valid_entry(m):
    return isinstance(m, dict) and m.get("id") and m.get("name")


class VaultEngine:
    def __init__(self, data_key, vault_dir=None):
        from cryptography.fernet import Fernet
        import base64 as _b64
        self.key = data_key
        self.fernet = Fernet(_b64.urlsafe_b64encode(data_key))
        self.vault_dir = vault_dir or config.VAULT_DIR
        os.makedirs(self.vault_dir, exist_ok=True)
        self.manifest_path = os.path.join(self.vault_dir, "manifest.json")
        self.recovered_from_backup = False
        self.manifest = self._load()

    def _blob_path(self, vid):
        return os.path.join(self.vault_dir, vid + ".suma")

    def _load(self):
        for p in (self.manifest_path, self.manifest_path + ".bak"):
            try:
                if os.path.isfile(p):
                    with open(p, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    if isinstance(data, list):
                        self.recovered_from_backup = (p != self.manifest_path)
                        return data
            except Exception:
                continue
        if os.path.isfile(self.manifest_path) or os.path.isfile(self.manifest_path + ".bak"):
            raise ManifestCorruptError(
                "manifest.json and its backup are both unreadable — "
                "refusing to overwrite them. Restore from a backup before continuing.")
        return []

    def _save(self):
        fd, tmp = tempfile.mkstemp(dir=self.vault_dir, suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(self.manifest, f, indent=2)
                f.flush()
                os.fsync(f.fileno())
            bak = self.manifest_path + ".bak"
            if os.path.isfile(self.manifest_path):
                os.replace(self.manifest_path, bak)
            os.replace(tmp, self.manifest_path)
        except Exception:
            if os.path.isfile(tmp):
                os.remove(tmp)
            raise

    def find(self, vid):
        return next((m for m in self.manifest if _valid_entry(m) and m["id"] == vid), None)

    def lock(self, path):
        if not os.path.exists(path):
            raise FileNotFoundError(f"not found: {path}")
        name = os.path.basename(path.rstrip(os.sep))
        is_dir = os.path.isdir(path)
        cat = utils.category_of(path)
        if is_dir:
            name = name + "/"
        vid = secrets.token_hex(8)
        final_blob = self._blob_path(vid)
        fd, tmp_blob = tempfile.mkstemp(dir=self.vault_dir, suffix=".tmp")
        os.close(fd)
        zip_tmp = None
        try:
            src = path
            if is_dir:
                zip_tmp = zip_dir_to_temp(path)
                src = zip_tmp
            encrypt_file(src, tmp_blob, self.fernet)
            self._verify_blob(tmp_blob, path, is_dir)
            os.replace(tmp_blob, final_blob)
        except Exception:
            if os.path.isfile(tmp_blob):
                os.remove(tmp_blob)
            raise
        finally:
            if zip_tmp and os.path.isfile(zip_tmp):
                os.remove(zip_tmp)
        entry = {
            "id": vid,
            "name": name,
            "orig": path,
            "dir": is_dir,
            "size": os.path.getsize(final_blob),
            "plain_size": None if is_dir else os.path.getsize(path),
            "cat": cat,
            "fmt": 2,
            "at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        }
        self.manifest.append(entry)
        self._save()
        warning = None
        try:
            if is_dir:
                shutil.rmtree(path)
            else:
                os.remove(path)
        except Exception as e:
            warning = (f"Encrypted copy is safe in the vault, but the original could not be "
                       f"removed and remains at: {path} ({e})")
        return {"ok": True, "name": name, "warning": warning}

    def _verify_blob(self, blob_path, orig_path, is_dir):
        fd, vtmp = tempfile.mkstemp(dir=self.vault_dir, suffix=".vrf")
        os.close(fd)
        try:
            decrypt_file(blob_path, vtmp, self.fernet)
            if is_dir:
                if zipfile.ZipFile(vtmp).testzip() is not None:
                    raise ValueError("verification failed: corrupt zip inside encrypted blob")
            else:
                if os.path.getsize(vtmp) != os.path.getsize(orig_path):
                    raise ValueError("verification failed: size mismatch after round-trip")
        finally:
            if os.path.isfile(vtmp):
                os.remove(vtmp)

    def unlock(self, vid):
        item = self.find(vid)
        if not item:
            raise KeyError(f"no vault item: {vid}")
        blob = self._blob_path(vid)
        if not os.path.isfile(blob):
            raise FileNotFoundError(f"encrypted data missing for {item['name']!r}")
        out = item["orig"]
        work = tempfile.mkdtemp(dir=self.vault_dir)
        try:
            dec_tmp = os.path.join(work, "data.bin")
            decrypt_file(blob, dec_tmp, self.fernet)
            if not item["dir"] and item.get("plain_size") is not None:
                if os.path.getsize(dec_tmp) != item["plain_size"]:
                    raise ValueError("size mismatch after decrypt — file may be damaged")
            if item["dir"]:
                ext_tmp = os.path.join(work, "ext")
                os.makedirs(ext_tmp)
                safe_extract(dec_tmp, ext_tmp)
                if os.path.isdir(out):
                    shutil.rmtree(out)
                elif os.path.lexists(out):
                    os.remove(out)
                shutil.move(ext_tmp, out)
            else:
                parent = os.path.dirname(out) or "."
                os.makedirs(parent, exist_ok=True)
                os.replace(dec_tmp, out)
        finally:
            shutil.rmtree(work, ignore_errors=True)
        os.remove(blob)
        self.manifest = [m for m in self.manifest if not (_valid_entry(m) and m["id"] == vid)]
        self._save()
        return item["name"]

    def remove(self, vid):
        p = self._blob_path(vid)
        if os.path.isfile(p):
            os.remove(p)
        item = self.find(vid)
        name = item["name"] if item else ""
        self.manifest = [m for m in self.manifest if not (_valid_entry(m) and m["id"] == vid)]
        self._save()
        return name
