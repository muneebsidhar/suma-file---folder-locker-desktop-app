import os
import sys
import json
import shutil
import tempfile
import zipfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ["XDG_DATA_HOME"] = tempfile.mkdtemp(prefix="suma_test_home_")

import config
import crypto
import utils
from vault import VaultEngine, ManifestCorruptError, safe_extract

PASS = []
def check(name, cond):
    PASS.append((name, bool(cond)))
    print(("PASS " if cond else "FAIL ") + name)

# ---------- 1. password hashing ----------
s, vs, tag, it = crypto.hash_password("hello12345")
check("v2 hash tuple", len(s) == 32 and len(vs) == 32 and it == 600_000)
cfg = {"salt": s, "ver_salt": vs, "hash": tag, "iter": it}
check("v2 verify ok", crypto.verify_password("hello12345", cfg))
check("v2 verify wrong", not crypto.verify_password("wrongpass1", cfg))

# legacy v1 compat (200k, plain pbkdf2 hex)
import hashlib
salt = os.urandom(16)
h = hashlib.pbkdf2_hmac("sha256", b"oldpassword", salt, 200_000).hex()
cfg1 = {"salt": salt.hex(), "hash": h}
check("v1 legacy verify ok", crypto.verify_password("oldpassword", cfg1))
check("v1 legacy verify wrong", not crypto.verify_password("nope12345", cfg1))
check("v1 needs upgrade", crypto.needs_upgrade(cfg1))
crypto.upgrade_hash(cfg1, "oldpassword")
check("upgraded verifies", crypto.verify_password("oldpassword", cfg1))
check("upgraded is v2", cfg1["iter"] == 600_000 and "ver_salt" in cfg1)

# ---------- 2. chunked file crypto ----------
from cryptography.fernet import Fernet
import base64
fernet = Fernet(base64.urlsafe_b64encode(os.urandom(32)))
tmp = tempfile.mkdtemp(prefix="suma_crypto_")

def rt(data, label):
    a = os.path.join(tmp, "a.bin"); b = os.path.join(tmp, "b.bin"); c = os.path.join(tmp, "c.bin")
    open(a, "wb").write(data)
    crypto.encrypt_file(a, b, fernet)
    ver = crypto.decrypt_file(b, c, fernet)
    check(f"roundtrip {label} ({ver})", open(c, "rb").read() == data)

rt(b"", "empty")
rt(b"hello", "tiny")
rt(os.urandom(3 * 1024 * 1024 + 123), "multi-chunk 3MB")

# v1 legacy blob compat
a = os.path.join(tmp, "v1a.bin"); b = os.path.join(tmp, "v1b.bin"); c = os.path.join(tmp, "v1c.bin")
open(a, "wb").write(b"legacy secret data")
open(b, "wb").write(fernet.encrypt(b"legacy secret data"))
ver = crypto.decrypt_file(b, c, fernet)
check(f"v1 legacy decrypt ({ver})", open(c, "rb").read() == b"legacy secret data")

# tamper detection
a = os.path.join(tmp, "t1.bin"); b = os.path.join(tmp, "t2.bin"); c = os.path.join(tmp, "t3.bin")
open(a, "wb").write(os.urandom(2 * 1024 * 1024))
crypto.encrypt_file(a, b, fernet)
blob = bytearray(open(b, "rb").read())
blob[100] ^= 0xFF
open(b, "wb").write(bytes(blob))
try:
    crypto.decrypt_file(b, c, fernet)
    check("tamper detected", False)
except Exception:
    check("tamper detected", True)

# ---------- 3. VaultEngine safe lock/unlock ----------
vd = tempfile.mkdtemp(prefix="suma_vault_")
eng = VaultEngine(os.urandom(32), vault_dir=vd)

work = tempfile.mkdtemp(prefix="suma_work_")
f1 = os.path.join(work, "notes.txt")
open(f1, "w").write("secret notes 123")
res = eng.lock(f1)
check("lock ok", res["ok"] and res["warning"] is None)
check("original removed after lock", not os.path.exists(f1))
check("manifest has entry", len(eng.manifest) == 1 and eng.manifest[0]["fmt"] == 2)

# empty file
f2 = os.path.join(work, "empty.txt")
open(f2, "w").close()
res2 = eng.lock(f2)
check("empty file lock ok", res2["ok"])

# nested folder
dd = os.path.join(work, "proj")
os.makedirs(os.path.join(dd, "sub", "deep"))
open(os.path.join(dd, "a.txt"), "w").write("A")
open(os.path.join(dd, "sub", "b.txt"), "w").write("B")
open(os.path.join(dd, "sub", "deep", "c.bin"), "wb").write(os.urandom(5000))
res3 = eng.lock(dd)
check("folder lock ok", res3["ok"] and eng.manifest[-1]["dir"])
check("folder removed after lock", not os.path.exists(dd))

# unlock file
vid1 = eng.manifest[0]["id"]
name = eng.unlock(vid1)
check("unlock file ok", name == "notes.txt" and open(f1).read() == "secret notes 123")

# unlock folder
vidf = [m for m in eng.manifest if m["dir"]][0]["id"]
eng.unlock(vidf)
check("unlock folder ok",
      open(os.path.join(dd, "a.txt")).read() == "A" and
      open(os.path.join(dd, "sub", "deep", "c.bin"), "rb").read() is not None and
      os.path.isfile(os.path.join(dd, "sub", "b.txt")))

# ---------- 4. manifest safety ----------
mf = os.path.join(vd, "manifest.json")
check("manifest written", os.path.isfile(mf))
# corrupt BOTH main and backup -> must raise, never silently empty
open(mf, "w").write("{corrupt json!!!")
if os.path.isfile(mf + ".bak"):
    open(mf + ".bak", "w").write("{also corrupt!!!")
try:
    VaultEngine(os.urandom(32), vault_dir=vd)
    check("both corrupt raises", False)
except ManifestCorruptError:
    check("both corrupt raises", True)
check("corrupt manifest NOT overwritten", "{corrupt" in open(mf).read())

# backup recovery: corrupt main, valid .bak
shutil.copy(os.path.join(vd, "manifest.json.bak") if os.path.isfile(os.path.join(vd, "manifest.json.bak")) else mf, mf + ".x")
# make a valid backup scenario fresh
vd2 = tempfile.mkdtemp(prefix="suma_vault2_")
e2 = VaultEngine(os.urandom(32), vault_dir=vd2)
f3 = os.path.join(work, "x.txt"); open(f3, "w").write("x")
e2.lock(f3)  # creates manifest + (no .bak on first save)
f4 = os.path.join(work, "y.txt"); open(f4, "w").write("y")
e2.lock(f4)  # second save -> .bak now exists with 1 entry
open(os.path.join(vd2, "manifest.json"), "w").write("garbage{{{")
e3 = VaultEngine(os.urandom(32), vault_dir=vd2)
check("recovers from .bak", len(e3.manifest) == 1 and e3.recovered_from_backup)

# ---------- 5. zip slip ----------
ztmp = os.path.join(tmp, "evil.zip")
with zipfile.ZipFile(ztmp, "w") as z:
    z.writestr("../../evil.txt", "pwned")
    z.writestr("/abs/path.txt", "pwned")
try:
    safe_extract(ztmp, os.path.join(tmp, "out"))
    check("zip slip blocked", False)
except ValueError:
    check("zip slip blocked", True)
check("no file escaped", not os.path.isfile(os.path.join(tmp, "evil.txt")))

# ---------- 6. config migration ----------
leg = tempfile.mkdtemp(prefix="suma_legacy_")
legcfg = os.path.join(leg, "suma_config.json")
json.dump({"salt": "ab" * 16, "hash": "cd" * 32, "iter": 200000,
           "ksalt": "ef" * 16, "enc_key": "00"}, open(legcfg, "w"))
legvault = os.path.join(leg, "vault")
os.makedirs(legvault)
json.dump([{"id": "x", "name": "f"}], open(os.path.join(legvault, "manifest.json"), "w"))
open(os.path.join(legvault, "deadbeef.suma"), "wb").write(b"blob")
old_cwd = os.getcwd()
os.chdir(leg)
try:
    import importlib
    importlib.reload(config)
    pth, cfgm, migrated = config.startup_config()
    check("legacy discovered+migrated", migrated and cfgm["salt"] == "ab" * 16)
    check("vault blobs migrated", os.path.isfile(os.path.join(config.VAULT_DIR, "deadbeef.suma")))
    check("uses new location", pth == config.CONFIG_PATH)
    check("legacy originals untouched", os.path.isfile(legcfg))
finally:
    os.chdir(old_cwd)

shutil.rmtree(tmp, ignore_errors=True)
shutil.rmtree(work, ignore_errors=True)
shutil.rmtree(vd, ignore_errors=True)
shutil.rmtree(vd2, ignore_errors=True)
shutil.rmtree(leg, ignore_errors=True)

fails = [n for n, ok in PASS if not ok]
print(f"\n{len(PASS) - len(fails)}/{len(PASS)} passed")
sys.exit(1 if fails else 0)
