import sys
import os
import json
import hashlib
import base64
import shutil
import zipfile
import tempfile
import time
from datetime import datetime

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLineEdit, QPushButton, QLabel, QStackedWidget, QFrame, QDialog,
    QFileDialog, QScrollArea, QSizePolicy, QSpacerItem, QMessageBox, QMenu,
    QSystemTrayIcon, QGraphicsOpacityEffect, QSplashScreen, QComboBox
)
from PySide6.QtCore import Qt, Signal, QPoint, QPointF, QRectF, QPropertyAnimation, QEasingCurve, QTimer, QSize, QEvent
from PySide6.QtGui import (
    QPainter, QPainterPath, QColor, QLinearGradient, QRadialGradient,
    QPen, QBrush, QFont, QIcon, QPixmap, QMouseEvent, QImage,
    qRed, qGreen, qBlue, qRgb, QShortcut, QKeySequence
)

QFont.insertSubstitution("Consolas", "DejaVu Sans Mono")
QFont.insertSubstitution("DejaVu Sans Mono", "Courier New")

NEON = "#00ff88"
BRIGHT = "#d1ffe6"
DIM = "#58b88a"
DARKB = "#14532d"
RED = "#ff4d4d"
ORANGE = "#ffb020"

ICON_PATHS = ["D:/SUMA/assets/samu_icon.png", "D:/SUMA/assets/suma_icon.png"]
APP_DIR = os.path.dirname(os.path.abspath(__file__))
VAULT_DIR = os.path.join(APP_DIR, "vault")

PBKDF2_ROUNDS = 200_000
RESIZE_M = 7
MIN_W, MIN_H = 960, 700


def mono(bold=False, size=10):
    f = QFont("Consolas", size)
    f.setBold(bold)
    return f


def find_icon():
    for p in ICON_PATHS:
        if os.path.isfile(p):
            pm = QPixmap(p)
            if not pm.isNull():
                return pm
    return QPixmap()


def hash_password(password, salt=None):
    if salt is None:
        salt = os.urandom(16)
    h = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PBKDF2_ROUNDS)
    return salt.hex(), h.hex()


def verify_password(password, salt_hex, hash_hex):
    _, h = hash_password(password, bytes.fromhex(salt_hex))
    return h == hash_hex


def master_fernet(password, ksalt_hex):
    return _kdf_fernet(password.encode("utf-8"), ksalt_hex)


def rec_fernet(rec_key, salt_hex):
    return _kdf_fernet(rec_key, salt_hex)


def _kdf_fernet(secret, salt_hex):
    from cryptography.fernet import Fernet
    raw = hashlib.pbkdf2_hmac("sha256", secret, bytes.fromhex(salt_hex), PBKDF2_ROUNDS, dklen=32)
    return Fernet(base64.urlsafe_b64encode(raw))


STEGO_MAGIC = b"SUMA1"


def _lsb_bits(im, nbits):
    w, h = im.width(), im.height()
    out = []
    for y in range(h):
        for x in range(w):
            c = im.pixel(x, y)
            for v in (qRed(c), qGreen(c), qBlue(c)):
                out.append(v & 1)
                if len(out) >= nbits:
                    return out
    return out


def _bits_to_bytes(bits):
    return bytes(int("".join(map(str, bits[i:i + 8])), 2) for i in range(0, len(bits), 8))


def _load_rgb32(image_path):
    im = QImage(image_path)
    if im.isNull():
        raise ValueError("Could not read that picture.")
    return im.convertToFormat(QImage.Format_RGB32)


def stego_hide(image_path, data):
    im = _load_rgb32(image_path)
    payload = STEGO_MAGIC + len(data).to_bytes(2, "big") + data
    bits = "".join(f"{b:08b}" for b in payload)
    w, h = im.width(), im.height()
    if len(bits) > w * h * 3:
        raise ValueError("Picture too small - pick a bigger one.")
    idx = 0
    for y in range(h):
        for x in range(w):
            c = im.pixel(x, y)
            vals = [qRed(c), qGreen(c), qBlue(c)]
            for i in range(3):
                if idx < len(bits):
                    vals[i] = (vals[i] & 0xFE) | (ord(bits[idx]) - 48)
                    idx += 1
            im.setPixel(x, y, qRgb(vals[0], vals[1], vals[2]))
            if idx >= len(bits):
                break
        if idx >= len(bits):
            break
    return im


def stego_extract(image_path):
    try:
        im = _load_rgb32(image_path)
    except ValueError:
        return None
    head = _bits_to_bytes(_lsb_bits(im, 56))
    if head[:5] != STEGO_MAGIC:
        return None
    ln = int.from_bytes(head[5:7], "big")
    if ln <= 0 or ln > 4096:
        return None
    full = _lsb_bits(im, 56 + ln * 8)
    return _bits_to_bytes(full[56:])


def config_candidates():
    cands = ["suma_config.json",
             os.path.join("suma_config", "suma_config.json"),
             os.path.join("suma_config", "config.json")]
    if os.path.isdir("suma_config"):
        for fn in os.listdir("suma_config"):
            if fn.endswith(".json"):
                cands.append(os.path.join("suma_config", fn))
    return cands


def find_config():
    for p in config_candidates():
        if os.path.isfile(p):
            try:
                with open(p, "r", encoding="utf-8") as f:
                    d = json.load(f)
                if "salt" in d and "hash" in d:
                    return p, d
            except Exception:
                pass
    return None, None


def save_config(data):
    if os.path.isdir("suma_config"):
        path = os.path.join("suma_config", "suma_config.json")
    else:
        path = "suma_config.json"
    save_config_to(path, data)
    return path


def save_config_to(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


CAT_COLORS = {"Folders": "#00ff88", "Video": "#00ccff", "Music": "#ffaa00",
              "Pics": "#ff5599", "Documents": "#b388ff"}
CAT_ORDER = ["Folders", "Video", "Music", "Pics", "Documents"]


def fmt_size(sz):
    if sz < 1024:
        return f"{sz} B"
    if sz < 1048576:
        return f"{sz // 1024} KB"
    if sz < 1073741824:
        return f"{sz / 1048576:.0f} MB"
    return f"{sz / 1073741824:.1f} GB"


def gen_password(n=16):
    import secrets
    import string
    alpha = string.ascii_letters + string.digits + "!@#$%^&*-_=+?"
    return "".join(secrets.choice(alpha) for _ in range(n))


def category_of(path):
    if os.path.isdir(path):
        return "Folders"
    ext = os.path.splitext(path)[1].lower()
    if ext in (".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp", ".svg", ".ico"):
        return "Pics"
    if ext in (".mp3", ".wav", ".flac", ".ogg", ".m4a", ".aac"):
        return "Music"
    if ext in (".mp4", ".mkv", ".avi", ".mov", ".wmv", ".webm"):
        return "Video"
    return "Documents"


class BackPanel(QWidget):
    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        g = QLinearGradient(0, 0, self.width(), self.height())
        g.setColorAt(0, QColor("#030806"))
        g.setColorAt(1, QColor("#04140c"))
        p.fillRect(self.rect(), g)
        pen = QPen(QColor(0, 255, 136, 14))
        pen.setWidth(1)
        p.setPen(pen)
        for x in range(0, self.width(), 40):
            p.drawLine(x, 0, x, self.height())
        for y in range(0, self.height(), 40):
            p.drawLine(0, y, self.width(), y)
        rg = QRadialGradient(self.width() / 2, self.height() / 2, 320)
        rg.setColorAt(0, QColor(0, 255, 136, 38))
        rg.setColorAt(1, QColor(0, 255, 136, 0))
        p.fillRect(self.rect(), QBrush(rg))


class TitleBar(QWidget):
    def __init__(self, parent, icon_pm):
        super().__init__(parent)
        self.setFixedHeight(36)
        self._drag = None
        self.setStyleSheet("background:#02060a; border-bottom:1px solid #14532d;")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(12, 0, 6, 0)
        lay.setSpacing(8)
        logo = QLabel()
        if icon_pm and not icon_pm.isNull():
            logo.setPixmap(icon_pm.scaled(20, 20, Qt.KeepAspectRatio, Qt.SmoothTransformation))
            logo.setFixedSize(20, 20)
        else:
            logo.setFixedSize(20, 20)
        lay.addWidget(logo)
        t1 = QLabel("SUMA")
        t1.setFont(mono(True, 11))
        t1.setStyleSheet(f"color:{DIM}; background:transparent; border:none;")
        lay.addWidget(t1)
        t2 = QLabel("File & Folder Locker")
        t2.setFont(mono(False, 9))
        t2.setStyleSheet(f"color:{DIM}; background:transparent; border:none;")
        lay.addWidget(t2)
        lay.addStretch()
        self.btn_min = self._mkbtn("—")
        self.btn_max = self._mkbtn("▢")
        self.btn_close = self._mkbtn("✕", close=True)
        self.btn_min.clicked.connect(parent.showMinimized)
        self.btn_max.clicked.connect(self._toggle_max)
        self.btn_close.clicked.connect(parent.close)
        lay.addWidget(self.btn_min)
        lay.addWidget(self.btn_max)
        lay.addWidget(self.btn_close)
        self._parent = parent

    def _mkbtn(self, txt, close=False):
        b = QPushButton(txt)
        b.setFixedSize(40, 30)
        b.setFont(mono(False, 11))
        hov = f"background:#ff4d4d; color:#ffffff;" if close else "background:#0a1f14;"
        b.setStyleSheet(
            f"QPushButton {{ color:{DIM}; background:transparent; border:none; }}"
            f"QPushButton:hover {{ {hov} }}"
        )
        b.setCursor(Qt.PointingHandCursor)
        return b

    def _toggle_max(self):
        if self._parent.isMaximized():
            self._parent.showNormal()
        else:
            self._parent.showMaximized()

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self._drag = e.globalPosition().toPoint() - self._parent.frameGeometry().topLeft()

    def mouseMoveEvent(self, e):
        if self._drag and not self._parent.isMaximized():
            self._parent.move(e.globalPosition().toPoint() - self._drag)

    def mouseReleaseEvent(self, e):
        self._drag = None


class LockGlyph(QLabel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(22, 22)
        self.setStyleSheet("background:transparent; border:none;")

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        pen = QPen(QColor(NEON))
        pen.setWidth(2)
        p.setPen(pen)
        p.drawArc(5, 3, 12, 10, 0, 180 * 16)
        p.setBrush(QBrush(QColor(NEON)))
        p.setPen(Qt.NoPen)
        p.drawRoundedRect(3, 9, 16, 11, 2, 2)


class EyeButton(QPushButton):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(40, 46)
        self.setCursor(Qt.PointingHandCursor)
        self.open = False
        self.setStyleSheet("QPushButton { background:transparent; border:none; }")

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        pen = QPen(QColor(NEON))
        pen.setWidth(2)
        p.setPen(pen)
        p.drawEllipse(9, 16, 22, 14)
        p.setBrush(QBrush(QColor(NEON)))
        p.setPen(Qt.NoPen)
        p.drawEllipse(17, 20, 6, 6)
        if not self.open:
            pen = QPen(QColor(NEON))
            pen.setWidth(2)
            p.setPen(pen)
            p.drawLine(8, 34, 32, 12)


class _FieldEdit(QLineEdit):
    def __init__(self, on_focus, on_blur, parent=None):
        super().__init__(parent)
        self._on_focus = on_focus
        self._on_blur = on_blur

    def focusInEvent(self, e):
        self._on_focus()
        super().focusInEvent(e)

    def focusOutEvent(self, e):
        self._on_blur()
        super().focusOutEvent(e)


class PasswordField(QWidget):
    def __init__(self, label_text, parent=None):
        super().__init__(parent)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(6)
        lab = QLabel(label_text.upper())
        lab.setFont(mono(True, 9))
        lab.setStyleSheet(f"color:{DIM}; background:transparent; border:none;")
        outer.addWidget(lab)
        box = QFrame()
        box.setFixedHeight(46)
        box.setStyleSheet(
            f"QFrame {{ background:#04100a; border:1.2px solid {DARKB}; border-radius:4px; }}"
        )
        hl = QHBoxLayout(box)
        hl.setContentsMargins(10, 0, 2, 0)
        hl.setSpacing(8)
        hl.addWidget(LockGlyph())
        self.edit = _FieldEdit(self._fin, self._fout)
        self.edit.setEchoMode(QLineEdit.Password)
        self.edit.setFocusPolicy(Qt.StrongFocus)
        self.edit.setFont(mono(False, 12))
        self.edit.setStyleSheet(
            f"QLineEdit {{ color:{BRIGHT}; background:transparent; border:none; }}"
        )
        hl.addWidget(self.edit, 1)
        self.eye = EyeButton()
        self.eye.clicked.connect(self.toggle)
        hl.addWidget(self.eye)
        outer.addWidget(box)
        self.box = box

    def _fin(self):
        self.box.setStyleSheet(
            f"QFrame {{ background:#04100a; border:1.2px solid {NEON}; border-radius:4px; }}"
        )

    def _fout(self):
        self.box.setStyleSheet(
            f"QFrame {{ background:#04100a; border:1.2px solid {DARKB}; border-radius:4px; }}"
        )

    def toggle(self):
        if self.edit.echoMode() == QLineEdit.Password:
            self.edit.setEchoMode(QLineEdit.Normal)
            self.eye.open = True
        else:
            self.edit.setEchoMode(QLineEdit.Password)
            self.eye.open = False
        self.eye.update()

    def text(self):
        return self.edit.text()

    def clear(self):
        self.edit.clear()


class StrengthMeter(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)
        row = QHBoxLayout()
        row.setSpacing(8)
        self.segs = []
        for _ in range(4):
            s = QFrame()
            s.setFixedHeight(5)
            s.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            s.setStyleSheet(f"background:{DARKB}; border:none;")
            row.addWidget(s)
            self.segs.append(s)
        lay.addLayout(row)
        self.lbl = QLabel("Strength: —")
        self.lbl.setFont(mono(True, 9))
        self.lbl.setStyleSheet(f"color:{DIM}; background:transparent; border:none;")
        lay.addWidget(self.lbl)

    def set_strength(self, pw):
        score = 0
        if len(pw) >= 8:
            score += 1
        if any(c.isupper() for c in pw) and any(c.islower() for c in pw):
            score += 1
        if any(c.isdigit() for c in pw):
            score += 1
        if any(not c.isalnum() for c in pw):
            score += 1
        names = [(1, "Weak", RED), (2, "Fair", ORANGE), (3, "Good", NEON), (4, "Strong", NEON)]
        if not pw:
            for s in self.segs:
                s.setStyleSheet(f"background:{DARKB}; border:none;")
            self.lbl.setText("Strength: —")
            self.lbl.setStyleSheet(f"color:{DIM}; background:transparent; border:none;")
            return
        level = max(1, min(4, score if score > 0 else 1))
        name, color = [(n, c) for lv, n, c in names if lv == level][0]
        for i, s in enumerate(self.segs):
            s.setStyleSheet(f"background:{color if i < level else DARKB}; border:none;")
        self.lbl.setText(f"Strength: {name}")
        self.lbl.setStyleSheet(f"color:{color}; background:transparent; border:none;")


class NeonButton(QPushButton):
    def __init__(self, text, parent=None):
        super().__init__(text, parent)
        self.setFixedHeight(50)
        self.setFont(mono(True, 11))
        self.setCursor(Qt.PointingHandCursor)
        self.setStyleSheet(
            f"""QPushButton {{
                color:#02140a; border:none; border-radius:4px;
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 {NEON}, stop:1 #00cc6a);
            }}
            QPushButton:hover {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #33ff9e, stop:1 #00e67a);
            }}
            QPushButton:pressed {{ background:#00b35c; }}"""
        )


class Card(QFrame):
    def __init__(self, w, h, parent=None):
        super().__init__(parent)
        self.setFixedSize(w, h)
        self.setStyleSheet(
            f"QFrame {{ background:#050f0a; border:1.5px solid {NEON}; border-radius:4px; }}"
        )

    def paintEvent(self, e):
        super().paintEvent(e)
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        pen = QPen(QColor(NEON))
        pen.setWidth(4)
        p.setPen(pen)
        L = 22
        ww, hh = self.width(), self.height()
        for sx, sy in [(1, 1), (-1, 1), (1, -1), (-1, -1)]:
            x0 = 2 if sx == 1 else ww - 2
            y0 = 2 if sy == 1 else hh - 2
            p.drawLine(x0, y0, x0 + sx * L, y0)
            p.drawLine(x0, y0, x0, y0 + sy * L)


class ActivityLog:
    def __init__(self):
        self.path = os.path.join(VAULT_DIR, "activity.json")
        self.events = []
        self.load()

    def load(self):
        try:
            if os.path.isfile(self.path):
                with open(self.path, "r", encoding="utf-8") as f:
                    self.events = json.load(f)
        except Exception:
            self.events = []

    def save(self):
        try:
            os.makedirs(VAULT_DIR, exist_ok=True)
            with open(self.path, "w", encoding="utf-8") as f:
                json.dump(self.events[-500:], f, indent=2)
        except Exception:
            pass

    def add(self, event, detail):
        self.events.append({
            "time": datetime.now().strftime("%H:%M:%S"),
            "date": datetime.now().strftime("%Y-%m-%d"),
            "event": event,
            "detail": detail,
        })
        self.save()

    def clear(self):
        self.events = []
        self.save()


class VaultEngine:
    def __init__(self, data_key):
        from cryptography.fernet import Fernet
        self.key = data_key
        self.fernet = Fernet(base64.urlsafe_b64encode(data_key))
        os.makedirs(VAULT_DIR, exist_ok=True)
        self.manifest_path = os.path.join(VAULT_DIR, "manifest.json")
        self.manifest = self._load()

    def _load(self):
        try:
            if os.path.isfile(self.manifest_path):
                with open(self.manifest_path, "r", encoding="utf-8") as f:
                    return json.load(f)
        except Exception:
            pass
        return []

    def _save(self):
        with open(self.manifest_path, "w", encoding="utf-8") as f:
            json.dump(self.manifest, f, indent=2)

    def lock(self, path):
        name = os.path.basename(path.rstrip(os.sep))
        blob_in = path
        is_dir = os.path.isdir(path)
        cat = "Folders" if is_dir else category_of(path)
        tmp = None
        if is_dir:
            tmp = tempfile.mktemp(suffix=".zip")
            shutil.make_archive(tmp[:-4], "zip", path)
            blob_in = tmp
            name = name + "/"
        with open(blob_in, "rb") as f:
            token = self.fernet.encrypt(f.read())
        vid = hashlib.sha256(os.urandom(16)).hexdigest()[:16]
        with open(os.path.join(VAULT_DIR, vid + ".suma"), "wb") as f:
            f.write(token)
        try:
            if is_dir:
                shutil.rmtree(path)
            else:
                os.remove(path)
        except Exception:
            pass
        if tmp and os.path.isfile(tmp):
            os.remove(tmp)
        self.manifest.append({
            "id": vid,
            "name": name,
            "orig": path,
            "dir": is_dir,
            "size": len(token),
            "cat": cat,
            "at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        })
        self._save()
        return name

    def unlock(self, vid, dest=None):
        item = next((m for m in self.manifest if m["id"] == vid), None)
        if not item:
            return None
        with open(os.path.join(VAULT_DIR, vid + ".suma"), "rb") as f:
            data = self.fernet.decrypt(f.read())
        out = dest or item["orig"]
        if item["dir"]:
            tmp = tempfile.mktemp(suffix=".zip")
            with open(tmp, "wb") as f:
                f.write(data)
            os.makedirs(out, exist_ok=True)
            with zipfile.ZipFile(tmp, "r") as z:
                z.extractall(out)
            os.remove(tmp)
        else:
            os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
            with open(out, "wb") as f:
                f.write(data)
        os.remove(os.path.join(VAULT_DIR, vid + ".suma"))
        self.manifest = [m for m in self.manifest if m["id"] != vid]
        self._save()
        return item["name"]

    def remove(self, vid):
        p = os.path.join(VAULT_DIR, vid + ".suma")
        if os.path.isfile(p):
            os.remove(p)
        name = next((m["name"] for m in self.manifest if m["id"] == vid), "")
        self.manifest = [m for m in self.manifest if m["id"] != vid]
        self._save()
        return name


class NameField(QWidget):
    def __init__(self, label_text, parent=None):
        super().__init__(parent)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(6)
        lab = QLabel(label_text)
        lab.setFont(mono(True, 9))
        lab.setStyleSheet(f"color:{DIM}; background:transparent; border:none;")
        outer.addWidget(lab)
        box = QFrame()
        box.setFixedHeight(46)
        box.setStyleSheet(
            f"QFrame {{ background:#04100a; border:1px solid {DARKB}; border-radius:4px; }}"
            f"QFrame:focus-within {{ border:1px solid {NEON}; }}")
        hl = QHBoxLayout(box)
        hl.setContentsMargins(12, 0, 12, 0)
        self.edit = QLineEdit()
        self.edit.setFont(mono(False, 13))
        self.edit.setStyleSheet(f"color:{BRIGHT}; background:transparent; border:none;")
        self.edit.setMaxLength(30)
        hl.addWidget(self.edit)
        outer.addWidget(box)

    def text(self):
        return self.edit.text().strip()

    def clear(self):
        self.edit.clear()


class SetupScreen(QWidget):
    password_set = Signal(bytes, bytes)

    def __init__(self, icon_pm, parent=None):
        super().__init__(parent)
        self.icon_pm = icon_pm
        self.avatar_src = None
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addStretch()
        wrap = QHBoxLayout()
        wrap.addStretch()
        self.card = Card(500, 648)
        cl = QVBoxLayout(self.card)
        cl.setContentsMargins(45, 26, 45, 24)
        cl.setSpacing(0)
        aw = QHBoxLayout()
        aw.addStretch()
        self.avatar = AvatarWidget(84, badge="plus")
        self.avatar.clicked.connect(self.pick_avatar)
        aw.addWidget(self.avatar)
        aw.addStretch()
        cl.addLayout(aw)
        cl.addSpacing(4)
        hint = QLabel("tap to add photo")
        hint.setFont(mono(False, 8))
        hint.setStyleSheet(f"color:{DIM}; background:transparent; border:none;")
        hint.setAlignment(Qt.AlignCenter)
        cl.addWidget(hint)
        cl.addSpacing(10)
        nr = QHBoxLayout()
        nr.setSpacing(12)
        self.fn = NameField("FIRST NAME")
        self.ln = NameField("LAST NAME")
        nr.addWidget(self.fn)
        nr.addWidget(self.ln)
        cl.addLayout(nr)
        cl.addSpacing(10)
        self.pw1 = PasswordField("MASTER PASSWORD")
        cl.addWidget(self.pw1)
        cl.addSpacing(8)
        self.pw2 = PasswordField("CONFIRM PASSWORD")
        cl.addWidget(self.pw2)
        cl.addSpacing(8)
        self.meter = StrengthMeter()
        cl.addWidget(self.meter)
        self.pw1.edit.textChanged.connect(self.meter.set_strength)
        cl.addSpacing(6)
        gen = QPushButton("↻ generate strong password")
        gen.setFont(mono(False, 9))
        gen.setCursor(Qt.PointingHandCursor)
        gen.setFlat(True)
        gen.setStyleSheet(f"color:{DIM}; background:transparent; border:none; text-decoration:underline;")
        gen.clicked.connect(self.gen_pw)
        gl = QHBoxLayout()
        gl.addStretch()
        gl.addWidget(gen)
        gl.addStretch()
        cl.addLayout(gl)
        cl.addSpacing(2)
        self.err = QLabel("")
        self.err.setFont(mono(True, 9))
        self.err.setStyleSheet(f"color:{RED}; background:transparent; border:none;")
        self.err.setAlignment(Qt.AlignCenter)
        self.err.setFixedHeight(18)
        cl.addWidget(self.err)
        self.btn = NeonButton("Set Password && Continue")
        self.btn.setFixedWidth(380)
        bl = QHBoxLayout()
        bl.addStretch()
        bl.addWidget(self.btn)
        bl.addStretch()
        cl.addLayout(bl)
        self.btn.clicked.connect(self.submit)
        cl.addSpacing(8)
        f = QLabel("Your password is never stored in plain text.")
        f.setFont(mono(False, 8))
        f.setStyleSheet(f"color:{DIM}; background:transparent; border:none;")
        f.setAlignment(Qt.AlignCenter)
        cl.addWidget(f)
        cl.addStretch()
        wrap.addWidget(self.card)
        wrap.addStretch()
        lay.addLayout(wrap)
        lay.addStretch()

    def pick_avatar(self):
        p, _ = QFileDialog.getOpenFileName(self, "Choose profile picture", "",
                                           "Images (*.png *.jpg *.jpeg *.bmp *.webp)")
        if p:
            pm = QPixmap(p)
            if not pm.isNull():
                s = min(pm.width(), pm.height())
                self.avatar.set_pixmap(pm.copy((pm.width() - s) // 2, (pm.height() - s) // 2, s, s))
                self.avatar_src = p

    def gen_pw(self):
        p = gen_password()
        self.pw1.edit.setText(p)
        self.pw2.edit.setText(p)
        self.meter.set_strength(p)

    def submit(self):
        fn = self.fn.text()
        if not fn:
            return self.fail("Please enter your first name.")
        a = self.pw1.text()
        b = self.pw2.text()
        if len(a) < 8:
            return self.fail("Password must be at least 8 characters.")
        if a != b:
            return self.fail("Passwords do not match.")
        if self.avatar_src:
            try:
                save_profile_pic(self.avatar_src)
            except Exception:
                pass
        salt, hh = hash_password(a)
        ksalt = os.urandom(16).hex()
        dk = os.urandom(32)
        enc = master_fernet(a, ksalt).encrypt(dk).decode()
        rec_key = os.urandom(32)
        rec_salt = os.urandom(16).hex()
        enc_rec = rec_fernet(rec_key, rec_salt).encrypt(dk).decode()
        save_config({"salt": salt, "hash": hh, "ksalt": ksalt, "enc_key": enc,
                     "rec_salt": rec_salt, "enc_key_rec": enc_rec,
                     "first_name": fn, "last_name": self.ln.text(),
                     "created": datetime.now().isoformat()})
        self.pw1.clear()
        self.pw2.clear()
        self.err.setText("")
        self.password_set.emit(dk, rec_key)

    def fail(self, msg):
        self.err.setText(msg)
        a = QPropertyAnimation(self.card, b"pos")
        x0 = self.card.pos().x()
        a.setDuration(300)
        a.setLoopCount(2)
        a.setKeyValueAt(0, QPoint(x0, self.card.pos().y()))
        a.setKeyValueAt(0.25, QPoint(x0 - 8, self.card.pos().y()))
        a.setKeyValueAt(0.75, QPoint(x0 + 8, self.card.pos().y()))
        a.setKeyValueAt(1, QPoint(x0, self.card.pos().y()))
        a.setEasingCurve(QEasingCurve.InOutQuad)
        a.start()


class UnlockScreen(QWidget):
    unlocked = Signal(object)
    forgot_req = Signal()

    def __init__(self, icon_pm, parent=None):
        super().__init__(parent)
        self.icon_pm = icon_pm
        self.attempts = 0
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addStretch()
        wrap = QHBoxLayout()
        wrap.addStretch()
        self.card = Card(470, 540)
        cl = QVBoxLayout(self.card)
        cl.setContentsMargins(45, 36, 45, 30)
        cl.setSpacing(0)
        if icon_pm and not icon_pm.isNull():
            logo = QLabel()
            logo.setPixmap(icon_pm.scaled(64, 64, Qt.KeepAspectRatio, Qt.SmoothTransformation))
            logo.setAlignment(Qt.AlignCenter)
            cl.addWidget(logo)
        t = QLabel("SUMA")
        t.setFont(mono(True, 20))
        t.setStyleSheet(f"color:{BRIGHT}; background:transparent; border:none; letter-spacing:7px;")
        t.setAlignment(Qt.AlignCenter)
        cl.addWidget(t)
        s = QLabel("> file_and_folder_locker")
        s.setFont(mono(False, 9))
        s.setStyleSheet(f"color:{DIM}; background:transparent; border:none;")
        s.setAlignment(Qt.AlignCenter)
        cl.addWidget(s)
        cl.addSpacing(18)
        h = QLabel("> Enter Master Password")
        h.setFont(mono(True, 18))
        h.setStyleSheet(f"color:{BRIGHT}; background:transparent; border:none;")
        h.setAlignment(Qt.AlignCenter)
        cl.addWidget(h)
        cl.addSpacing(8)
        for line in ["Enter your master password", "to unlock the vault."]:
            sl = QLabel(line)
            sl.setFont(mono(False, 10))
            sl.setStyleSheet(f"color:{DIM}; background:transparent; border:none;")
            sl.setAlignment(Qt.AlignCenter)
            cl.addWidget(sl)
        cl.addSpacing(18)
        self.pw = PasswordField("MASTER PASSWORD")
        cl.addWidget(self.pw)
        self.pw.edit.returnPressed.connect(self.submit)
        cl.addSpacing(8)
        self.err = QLabel("")
        self.err.setFont(mono(True, 9))
        self.err.setStyleSheet(f"color:{RED}; background:transparent; border:none;")
        self.err.setAlignment(Qt.AlignCenter)
        self.err.setFixedHeight(18)
        cl.addWidget(self.err)
        self.btn = NeonButton("Unlock Vault")
        self.btn.setFixedWidth(380)
        bl = QHBoxLayout()
        bl.addStretch()
        bl.addWidget(self.btn)
        bl.addStretch()
        cl.addLayout(bl)
        self.btn.clicked.connect(self.submit)
        cl.addSpacing(10)
        fw = QHBoxLayout()
        fw.addStretch()
        f = QPushButton("Forgot password?")
        f.setFont(mono(False, 8))
        f.setCursor(Qt.PointingHandCursor)
        f.setFlat(True)
        f.setStyleSheet(f"color:{DIM}; background:transparent; border:none; text-decoration:underline;")
        f.clicked.connect(lambda: self.forgot_req.emit())
        fw.addWidget(f)
        fw.addStretch()
        cl.addLayout(fw)
        cl.addStretch()
        wrap.addWidget(self.card)
        wrap.addStretch()
        lay.addLayout(wrap)
        lay.addStretch()

    def submit(self):
        _, cfg = find_config()
        if not cfg:
            self.err.setText("No vault config found.")
            return
        if verify_password(self.pw.text(), cfg["salt"], cfg["hash"]):
            dk = master_fernet(self.pw.text(), cfg["ksalt"]).decrypt(cfg["enc_key"].encode())
            self.pw.clear()
            self.err.setText("")
            self.attempts = 0
            self.unlocked.emit(dk)
        else:
            self.attempts += 1
            left = 5 - self.attempts
            if left <= 0:
                self.err.setText("Too many attempts. Wait 30 seconds.")
                self.btn.setEnabled(False)
                QTimer.singleShot(30000, lambda: (self.btn.setEnabled(True), setattr(self, "attempts", 0)))
            else:
                self.err.setText(f"Wrong password. {left} attempts remaining.")
            a = QPropertyAnimation(self.card, b"pos")
            x0 = self.card.pos().x()
            a.setDuration(300)
            a.setLoopCount(2)
            a.setKeyValueAt(0, QPoint(x0, self.card.pos().y()))
            a.setKeyValueAt(0.25, QPoint(x0 - 8, self.card.pos().y()))
            a.setKeyValueAt(0.75, QPoint(x0 + 8, self.card.pos().y()))
            a.setKeyValueAt(1, QPoint(x0, self.card.pos().y()))
            a.start()


class CatIcon(QLabel):
    def __init__(self, kind, parent=None):
        super().__init__(parent)
        self.kind = kind
        self.active = False
        self.setFixedSize(44, 44)
        self.setStyleSheet("background:transparent; border:none;")

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        col = QColor(NEON) if self.active else QColor(DIM)
        p.setPen(QPen(col, 3))
        cx, cy, s = 22, 22, 34
        if self.kind == "Pics":
            p.drawRoundedRect(int(cx - s / 2), int(cy - s / 2), s, s, 4, 4)
            p.drawLine(int(cx - s / 2 + 4), int(cy + s / 2 - 4), int(cx - 2), int(cy - 6))
            p.drawLine(int(cx - 2), int(cy - 6), int(cx + s / 2 - 4), int(cy + s / 2 - 4))
        elif self.kind == "Music":
            p.drawEllipse(int(cx - 12), int(cy + 2), 12, 9)
            p.drawLine(int(cx - 2), int(cy + 6), int(cx - 2), int(cy - 12))
            p.drawLine(int(cx - 2), int(cy - 12), int(cx + 12), int(cy - 8))
        elif self.kind == "Video":
            p.drawRoundedRect(int(cx - s / 2), int(cy - 12), s, 24, 5, 5)
            p.setBrush(QBrush(col))
            p.setPen(Qt.NoPen)
            p.drawPolygon([QPoint(int(cx - 5), int(cy - 6)), QPoint(int(cx - 5), int(cy + 6)),
                           QPoint(int(cx + 8), int(cy))])
        elif self.kind == "Folders":
            p.drawRoundedRect(int(cx - 15), int(cy - 12), 16, 8, 2, 2)
            p.drawRoundedRect(int(cx - 17), int(cy - 8), 34, 20, 4, 4)
        else:
            p.drawPolygon([QPoint(int(cx - 10), int(cy - 14)), QPoint(int(cx + 4), int(cy - 14)),
                           QPoint(int(cx + 12), int(cy - 6)), QPoint(int(cx + 12), int(cy + 14)),
                           QPoint(int(cx - 10), int(cy + 14))])


def profile_path():
    return os.path.join(APP_DIR, "profile.png")


def save_profile_pic(src):
    pm = QPixmap(src)
    if pm.isNull():
        raise ValueError("Could not read that image.")
    pm = pm.scaled(256, 256, Qt.KeepAspectRatio, Qt.SmoothTransformation)
    if not pm.save(profile_path(), "PNG"):
        raise IOError("Could not save profile picture.")


def load_avatar_pm():
    pm = QPixmap()
    pp = profile_path()
    if os.path.isfile(pp):
        pm = QPixmap(pp)
        if not pm.isNull():
            s = min(pm.width(), pm.height())
            pm = pm.copy((pm.width() - s) // 2, (pm.height() - s) // 2, s, s)
    return pm


class AvatarWidget(QLabel):
    clicked = Signal()

    def __init__(self, d=84, badge=None, parent=None):
        super().__init__(parent)
        self._d = d
        self._badge = badge
        self._pm = QPixmap()
        self.setFixedSize(d, d)
        self.setCursor(Qt.PointingHandCursor)
        self.setStyleSheet("background:transparent; border:none;")

    def set_pixmap(self, pm):
        self._pm = pm if pm and not pm.isNull() else QPixmap()
        self.update()

    def mousePressEvent(self, e):
        self.clicked.emit()

    def paintEvent(self, e):
        d = self._d
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        path = QPainterPath()
        path.addEllipse(3, 3, d - 6, d - 6)
        p.setClipPath(path)
        if self._pm and not self._pm.isNull():
            p.drawPixmap(3, 3, d - 6, d - 6, self._pm)
        else:
            p.fillRect(0, 0, d, d, QColor(DARKB))
            p.setPen(Qt.NoPen)
            p.setBrush(QColor("#0e3a24"))
            cx = d / 2
            p.drawEllipse(QPointF(cx, d * 0.36), d * 0.14, d * 0.14)
            p.drawEllipse(QPointF(cx, d * 0.92), d * 0.30, d * 0.30)
        p.setClipping(False)
        p.setPen(QPen(QColor(NEON), 2))
        p.setBrush(Qt.NoBrush)
        p.drawEllipse(3, 3, d - 6, d - 6)
        if self._badge:
            bs = 24
            bx, by = d - bs - 1, d - bs - 1
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(NEON))
            p.drawEllipse(bx, by, bs, bs)
            p.setPen(QColor("#02140a"))
            p.setFont(mono(True, 13))
            p.drawText(bx, by, bs, bs, Qt.AlignCenter, "+" if self._badge == "plus" else "✎")
        p.end()


class Sidebar(QWidget):
    nav_req = Signal(str)
    lock_req = Signal()

    def __init__(self, active="vault", parent=None):
        super().__init__(parent)
        self._active = active
        self.setFixedWidth(230)
        self.setStyleSheet("background:#040d08; border-right:1px solid #14532d;")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(18, 26, 18, 18)
        lay.setSpacing(0)
        aw = QHBoxLayout()
        aw.addStretch()
        self.avatar = AvatarWidget(84, badge="pencil")
        self.avatar.clicked.connect(self.change_pic)
        aw.addWidget(self.avatar)
        aw.addStretch()
        lay.addLayout(aw)
        lay.addSpacing(10)
        hello = QLabel("Hello!")
        hello.setFont(mono(False, 10))
        hello.setStyleSheet(f"color:{DIM}; background:transparent; border:none;")
        hello.setAlignment(Qt.AlignCenter)
        lay.addWidget(hello)
        self.name_lbl = QLabel("User")
        self.name_lbl.setFont(mono(True, 14))
        self.name_lbl.setStyleSheet(f"color:{BRIGHT}; background:transparent; border:none;")
        self.name_lbl.setAlignment(Qt.AlignCenter)
        self.name_lbl.setWordWrap(True)
        lay.addWidget(self.name_lbl)
        lay.addSpacing(26)
        self._btns = {}
        for key, label in [("vault", "> vault"), ("log", "> activity log"), ("settings", "> settings")]:
            b = QPushButton(label)
            b.setFixedHeight(44)
            b.setFont(mono(True, 11))
            b.setCursor(Qt.PointingHandCursor)
            b.setStyleSheet("background:transparent; border:none; text-align:left; padding-left:12px;")
            b.clicked.connect(lambda _=False, k=key: self.nav_req.emit(k))
            lay.addWidget(b)
            self._btns[key] = b
        lay.addStretch()
        self.refresh_nav()
        self.lock_btn = QPushButton("lock now")
        self.lock_btn.setFixedHeight(38)
        self.lock_btn.setFont(mono(True, 11))
        self.lock_btn.setCursor(Qt.PointingHandCursor)
        self.lock_btn.setStyleSheet(
            f"""QPushButton {{ color:{DIM}; background:transparent; border:1.5px solid {DARKB}; border-radius:4px; }}
                QPushButton:hover {{ color:{NEON}; border:1.5px solid {NEON}; background:#0a1f14; }}"""
        )
        self.lock_btn.clicked.connect(lambda: self.lock_req.emit())
        lay.addWidget(self.lock_btn)
        lay.addSpacing(40)
        c1 = QLabel("MUNEEB UR REHMAN ©")
        c1.setFont(mono(True, 8))
        c1.setStyleSheet(f"color:{DIM}; background:transparent; border:none;")
        c1.setAlignment(Qt.AlignCenter)
        c1.setWordWrap(True)
        lay.addWidget(c1)
        c2 = QLabel("All Rights Reserved")
        c2.setFont(mono(False, 8))
        c2.setStyleSheet(f"color:{DIM}; background:transparent; border:none;")
        c2.setAlignment(Qt.AlignCenter)
        lay.addWidget(c2)

    def refresh_nav(self):
        for key, b in self._btns.items():
            if key == self._active:
                b.setStyleSheet(
                    f"color:{NEON}; background:#0a1f14; border:1px solid {NEON}; "
                    f"border-radius:4px; text-align:left; padding-left:12px;")
            else:
                b.setStyleSheet(
                    f"color:{DIM}; background:transparent; border:1px solid transparent; "
                    f"border-radius:4px; text-align:left; padding-left:12px;")

    def refresh_profile(self):
        self.avatar.set_pixmap(load_avatar_pm())
        _, cfg = find_config()
        name = ((cfg or {}).get("first_name") or "").strip() or "User"
        self.name_lbl.setText(name)

    def change_pic(self):
        if os.path.isfile(profile_path()):
            menu = QMenu(self)
            menu.setStyleSheet(
                f"QMenu {{ background:#050f0a; border:1px solid {NEON}; color:{BRIGHT}; }}"
                f"QMenu::item {{ padding:8px 24px; }}"
                f"QMenu::item:selected {{ background:#0a1f14; color:{NEON}; }}")
            menu.setFont(mono(False, 10))
            act_change = menu.addAction("Change picture")
            act_del = menu.addAction("Delete picture")
            pos = self.avatar.mapToGlobal(QPoint(self.avatar.width() - 12, self.avatar.height() - 12))
            act = menu.exec(pos)
            if act == act_change:
                self.browse_pic()
            elif act == act_del:
                if confirm_box(self, "> Delete picture?", "Remove your profile picture?"):
                    try:
                        os.remove(profile_path())
                    except Exception:
                        pass
                    self.avatar.set_pixmap(load_avatar_pm())
                    win = self.window()
                    if hasattr(win, "log") and getattr(win, "engine", None):
                        win.log.add("PROFILE DELETED", "profile picture removed")
        else:
            self.browse_pic()

    def browse_pic(self):
        p, _ = QFileDialog.getOpenFileName(self, "Choose profile picture", "",
                                           "Images (*.png *.jpg *.jpeg *.bmp *.webp)")
        if p:
            try:
                save_profile_pic(p)
            except Exception:
                return
            self.avatar.set_pixmap(load_avatar_pm())
            win = self.window()
            if hasattr(win, "log") and getattr(win, "engine", None):
                win.log.add("PROFILE UPDATED", "profile picture changed")


class CatCard(QFrame):

    clicked = Signal(str)

    def __init__(self, name, count, size, active=False, parent=None):
        super().__init__(parent)
        self.name = name
        self.setMinimumSize(128, 150)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setCursor(Qt.PointingHandCursor)
        self.active = active
        self.setStyleSheet(
            f"""QFrame {{
                background:#050f0a; border:{'3px' if active else '1px'} solid {NEON if active else DARKB};
                border-radius:6px;
            }}"""
        )
        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 12, 8, 12)
        lay.setSpacing(4)
        self.icon = CatIcon(name)
        self.icon.active = active
        lay.addWidget(self.icon, alignment=Qt.AlignCenter)
        n = QLabel(name)
        n.setFont(mono(True, 11))
        n.setStyleSheet(f"color:{BRIGHT}; background:transparent; border:none;")
        n.setAlignment(Qt.AlignCenter)
        lay.addWidget(n)
        self.info = QLabel(f"{count} items · {size}")
        self.info.setFont(mono(False, 9))
        self.info.setStyleSheet(f"color:{DIM}; background:transparent; border:none;")
        self.info.setAlignment(Qt.AlignCenter)
        lay.addWidget(self.info)

    def mousePressEvent(self, e):
        self.clicked.emit(self.name)


class FileRow(QFrame):
    unlock_req = Signal(str)
    remove_req = Signal(str)

    def __init__(self, item, parent=None):
        super().__init__(parent)
        self.vid = item["id"]
        self.setFixedHeight(64)
        self.setStyleSheet(
            f"QFrame {{ background:#050f0a; border:1px solid {DARKB}; border-radius:4px; }}"
        )
        lay = QHBoxLayout(self)
        lay.setContentsMargins(14, 0, 10, 0)
        lay.setSpacing(10)
        ic = QLabel("▤")
        ic.setFont(mono(False, 16))
        ic.setStyleSheet(f"color:{DIM}; background:transparent; border:none;")
        lay.addWidget(ic)
        tx = QVBoxLayout()
        tx.setSpacing(0)
        n = QLabel(item["name"])
        n.setFont(mono(True, 10))
        n.setStyleSheet(f"color:{BRIGHT}; background:transparent; border:none;")
        tx.addWidget(n)
        pp = QLabel(item["orig"])
        pp.setFont(mono(False, 8))
        pp.setStyleSheet(f"color:{DIM}; background:transparent; border:none;")
        tx.addWidget(pp)
        lay.addLayout(tx, 1)
        sz = QLabel(f"{item['size'] // 1024} KB" if item["size"] < 1048576 else f"{item['size'] / 1048576:.1f} MB")
        sz.setFont(mono(False, 10))
        sz.setStyleSheet(f"color:{DIM}; background:transparent; border:none;")
        sz.setFixedWidth(90)
        lay.addWidget(sz)
        pill = QLabel("LOCKED")
        pill.setFont(mono(True, 9))
        pill.setStyleSheet(
            f"color:{NEON}; background:transparent; border:2px solid {NEON}; border-radius:10px; padding:3px 10px;"
        )
        lay.addWidget(pill)
        ub = QPushButton("⇪")
        ub.setFixedSize(34, 30)
        ub.setFont(mono(False, 13))
        ub.setCursor(Qt.PointingHandCursor)
        ub.setStyleSheet(f"QPushButton {{ color:{NEON}; background:transparent; border:none; }}")
        ub.setToolTip("Unlock")
        ub.clicked.connect(lambda: self.unlock_req.emit(self.vid))
        lay.addWidget(ub)
        rb = QPushButton("×")
        rb.setFixedSize(34, 30)
        rb.setFont(mono(True, 14))
        rb.setCursor(Qt.PointingHandCursor)
        rb.setStyleSheet(f"QPushButton {{ color:{RED}; background:transparent; border:none; }}")
        rb.setToolTip("Remove from vault (keeps it locked)")
        rb.clicked.connect(lambda: self.remove_req.emit(self.vid))
        lay.addWidget(rb)


class DashboardScreen(QWidget):
    add_req = Signal()
    nav_req = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.cat = "Folders"
        self.search_text = ""
        self.sort_mode = "Name"
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        main = QHBoxLayout()
        main.setContentsMargins(0, 0, 0, 0)
        main.setSpacing(0)
        self.sidebar = Sidebar("vault")
        self.sidebar.nav_req.connect(lambda k: self.nav_req.emit({"vault": "Vault", "log": "Activity Log", "settings": "Settings"}[k]))
        main.addWidget(self.sidebar)
        body = QWidget()
        bl = QVBoxLayout(body)
        bl.setContentsMargins(40, 18, 40, 10)
        bl.setSpacing(12)
        top = QHBoxLayout()
        ct = QLabel("> Categories")
        ct.setFont(mono(True, 12))
        ct.setStyleSheet(f"color:{DIM}; background:transparent; border:none;")
        top.addWidget(ct)
        top.addStretch()
        self.add_btn = QPushButton("Add+")
        self.add_btn.setFixedSize(110, 36)
        self.add_btn.setFont(mono(True, 11))
        self.add_btn.setCursor(Qt.PointingHandCursor)
        self.add_btn.setStyleSheet(
            f"""QPushButton {{ color:{NEON}; background:transparent; border:2px solid {NEON}; border-radius:4px; }}
                QPushButton:hover {{ background:#0a1f14; }}"""
        )
        self.add_btn.clicked.connect(lambda: self.add_req.emit())
        top.addWidget(self.add_btn)
        bl.addLayout(top)
        cards = QHBoxLayout()
        cards.setSpacing(10)
        self.cat_cards = {}
        for name, count, size in [("Folders", 0, "0"), ("Video", 0, "0"), ("Music", 0, "0"),
                                   ("Pics", 0, "0"), ("Documents", 0, "0")]:
            c = CatCard(name, count, size, active=(name == self.cat))
            c.clicked.connect(self.set_cat)
            cards.addWidget(c)
            self.cat_cards[name] = c
        cards.addStretch()
        bl.addLayout(cards)
        hdr = QLabel("> Files")
        hdr.setFont(mono(True, 12))
        hdr.setStyleSheet(f"color:{DIM}; background:transparent; border:none;")
        bl.addWidget(hdr)
        mrow = QHBoxLayout()
        mrow.setSpacing(10)
        self.meter_bar = QFrame()
        self.meter_bar.setFixedHeight(8)
        self.meter_bar.setStyleSheet(
            f"QFrame {{ background:#04100a; border:1px solid {DARKB}; border-radius:4px; }}")
        self.meter_lay = QHBoxLayout(self.meter_bar)
        self.meter_lay.setContentsMargins(2, 2, 2, 2)
        self.meter_lay.setSpacing(2)
        mrow.addWidget(self.meter_bar, 1)
        self.meter_total = QLabel("0 B total")
        self.meter_total.setFont(mono(True, 10))
        self.meter_total.setStyleSheet(f"color:{DIM}; background:transparent; border:none;")
        mrow.addWidget(self.meter_total)
        bl.addLayout(mrow)
        tools = QHBoxLayout()
        tools.setSpacing(10)
        self.search = QLineEdit()
        self.search.setPlaceholderText("search vault...")
        self.search.setFont(mono(False, 10))
        self.search.setStyleSheet(
            f"""QLineEdit {{ color:{BRIGHT}; background:#04100a; border:1px solid {DARKB};
                border-radius:4px; padding:7px 10px; }}
                QLineEdit:focus {{ border:1px solid {NEON}; }}""")
        self.search.textChanged.connect(self.on_search)
        tools.addWidget(self.search, 1)
        self.sortbox = QComboBox()
        self.sortbox.addItems(["Name", "Newest", "Oldest", "Largest", "Smallest"])
        self.sortbox.setFont(mono(False, 10))
        self.sortbox.setStyleSheet(
            f"""QComboBox {{ color:{BRIGHT}; background:#04100a; border:1px solid {DARKB};
                border-radius:4px; padding:6px 10px; }}
                QComboBox QAbstractItemView {{ background:#050f0a; color:{BRIGHT};
                selection-background-color:#0a1f14; selection-color:{NEON}; border:1px solid {NEON}; }}
                QComboBox::drop-down {{ border:none; }}""")
        self.sortbox.currentTextChanged.connect(self.on_sort)
        tools.addWidget(self.sortbox)
        bl.addLayout(tools)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setStyleSheet("QScrollArea { background:transparent; border:none; }")
        self.scroll.viewport().setStyleSheet("background:transparent;")
        self.listw = QWidget()
        self.listl = QVBoxLayout(self.listw)
        self.listl.setContentsMargins(0, 0, 0, 0)
        self.listl.setSpacing(10)
        self.listl.addStretch()
        self.scroll.setWidget(self.listw)
        bl.addWidget(self.scroll, 1)
        main.addWidget(body, 1)
        lay.addLayout(main, 1)
        bar = QWidget()
        bar.setFixedHeight(34)
        bar.setStyleSheet("background:#02060a; border-top:1px solid #14532d;")
        brl = QHBoxLayout(bar)
        brl.setContentsMargins(20, 0, 0, 0)
        dot = QLabel("●")
        dot.setFont(mono(False, 10))
        dot.setStyleSheet(f"color:{NEON}; background:transparent; border:none;")
        brl.addWidget(dot)
        self.stat = QLabel("")
        self.stat.setFont(mono(False, 10))
        self.stat.setStyleSheet(f"color:{DIM}; background:transparent; border:none;")
        brl.addWidget(self.stat)
        brl.addStretch()
        lay.addWidget(bar)

    def on_search(self, t):
        self.search_text = t.strip().lower()
        self.refresh()

    def on_sort(self, t):
        self.sort_mode = t
        self.refresh()

    def set_cat(self, name):
        self.cat = name
        for n, c in self.cat_cards.items():
            c.active = (n == name)
            c.icon.active = (n == name)
            c.icon.update()
            c.setStyleSheet(
                f"""QFrame {{
                    background:#050f0a; border:{'3px' if c.active else '1px'} solid {NEON if c.active else DARKB};
                    border-radius:6px;
                }}"""
            )
            c.update()
        self.refresh()

    def refresh(self):
        win = self.window()
        if not getattr(win, "engine", None):
            return
        counts = {}
        sizes = {}
        for m in win.engine.manifest:
            counts[m["cat"]] = counts.get(m["cat"], 0) + 1
            sizes[m["cat"]] = sizes.get(m["cat"], 0) + m["size"]
        for n, c in self.cat_cards.items():
            cnt = counts.get(n, 0)
            sz = sizes.get(n, 0)
            c.info.setText(f"{cnt} item{'s' if cnt != 1 else ''} · {fmt_size(sz)}")
        total_bytes = sum(sizes.values())
        while self.meter_lay.count():
            w = self.meter_lay.takeAt(0).widget()
            if w:
                w.deleteLater()
        for n in CAT_ORDER:
            sz = sizes.get(n, 0)
            if sz > 0:
                seg = QWidget()
                seg.setStyleSheet(f"background:{CAT_COLORS[n]}; border:none; border-radius:2px;")
                self.meter_lay.addWidget(seg, stretch=max(1, int(sz)))
        self.meter_lay.addStretch(0)
        self.meter_total.setText(f"{fmt_size(total_bytes)} total")
        items = [m for m in win.engine.manifest if m["cat"] == self.cat]
        if self.search_text:
            items = [m for m in items if self.search_text in m["name"].lower()]
        if self.sort_mode == "Name":
            items.sort(key=lambda m: m["name"].lower())
        elif self.sort_mode == "Newest":
            items.sort(key=lambda m: m.get("at", ""), reverse=True)
        elif self.sort_mode == "Oldest":
            items.sort(key=lambda m: m.get("at", ""))
        elif self.sort_mode == "Largest":
            items.sort(key=lambda m: m["size"], reverse=True)
        elif self.sort_mode == "Smallest":
            items.sort(key=lambda m: m["size"])
        while self.listl.count() > 1:
            w = self.listl.takeAt(0).widget()
            if w:
                w.deleteLater()
        if not items:
            msg = (f"> no locked {self.cat.lower()} yet — click Add+"
                   if not self.search_text else "> nothing matches your search")
            e = QLabel(msg)
            e.setFont(mono(False, 11))
            e.setStyleSheet(f"color:{DIM}; background:transparent; border:none; padding:20px;")
            e.setAlignment(Qt.AlignCenter)
            self.listl.insertWidget(0, e)
        for it in items:
            r = FileRow(it)
            r.unlock_req.connect(win.unlock_item)
            r.remove_req.connect(win.remove_item)
            self.listl.insertWidget(0, r)
        total = len(win.engine.manifest)
        self.stat.setText(f"vault secured  ·  {total} items locked")


def confirm_box(parent, title, text):
    b = QMessageBox(parent)
    b.setWindowTitle("SUMA")
    b.setText(title + "\n\n" + text)
    b.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
    b.setDefaultButton(QMessageBox.No)
    b.setStyleSheet(
        f"""QMessageBox {{ background:#050f0a; }}
            QLabel {{ color:{BRIGHT}; background:transparent; font-family:Consolas; }}
            QPushButton {{ color:{NEON}; background:transparent; border:1.5px solid {NEON};
                          border-radius:4px; padding:8px 22px;
                          font-family:Consolas; font-weight:bold; }}
            QPushButton:hover {{ background:#0a1f14; }}"""
    )
    return b.exec() == QMessageBox.Yes


class PasswordPrompt(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Dialog)
        self.setModal(True)
        self.setFixedSize(420, 300)
        self.pw = None
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        body = QWidget()
        body.setStyleSheet(f"background:#050f0a; border:1.5px solid {NEON};")
        bl = QVBoxLayout(body)
        bl.setContentsMargins(36, 28, 36, 28)
        bl.setSpacing(12)
        t = QLabel("> Confirm Master Password")
        t.setFont(mono(True, 13))
        t.setStyleSheet(f"color:{BRIGHT}; background:transparent; border:none;")
        t.setAlignment(Qt.AlignCenter)
        bl.addWidget(t)
        s = QLabel("Enter your master password to continue.")
        s.setFont(mono(False, 10))
        s.setStyleSheet(f"color:{DIM}; background:transparent; border:none;")
        s.setAlignment(Qt.AlignCenter)
        bl.addWidget(s)
        self.field = PasswordField("MASTER PASSWORD")
        self.field.edit.returnPressed.connect(self.try_ok)
        bl.addWidget(self.field)
        self.err = QLabel("")
        self.err.setFont(mono(True, 9))
        self.err.setStyleSheet(f"color:{RED}; background:transparent; border:none;")
        self.err.setAlignment(Qt.AlignCenter)
        bl.addWidget(self.err)
        row = QHBoxLayout()
        cancel = QPushButton("Cancel")
        cancel.setFixedSize(120, 42)
        cancel.setFont(mono(True, 10))
        cancel.setCursor(Qt.PointingHandCursor)
        cancel.setStyleSheet(
            f"QPushButton {{ color:{DIM}; background:transparent; border:2px solid {DIM}; border-radius:4px; }}")
        cancel.clicked.connect(self.reject)
        row.addWidget(cancel)
        row.addStretch()
        ok = NeonButton("Confirm")
        ok.setFixedSize(140, 42)
        ok.clicked.connect(self.try_ok)
        row.addWidget(ok)
        bl.addLayout(row)
        lay.addWidget(body)

    def try_ok(self):
        _, cfg = find_config()
        if cfg and verify_password(self.field.text(), cfg["salt"], cfg["hash"]):
            self.pw = self.field.text()
            self.accept()
        else:
            self.err.setText("Wrong password.")


def ask_password(parent):
    d = PasswordPrompt(parent)
    if d.exec():
        return d.pw
    return None


class AddDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Dialog)
        self.setModal(True)
        self.setFixedSize(560, 500)
        self.setAcceptDrops(True)
        self.paths = []
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        bar = QWidget()
        bar.setFixedHeight(36)
        bar.setStyleSheet("background:#02060a; border-bottom:1px solid #14532d;")
        bl = QHBoxLayout(bar)
        bl.setContentsMargins(16, 0, 8, 0)
        t = QLabel("> Add to Vault")
        t.setFont(mono(True, 13))
        t.setStyleSheet(f"color:{BRIGHT}; background:transparent; border:none;")
        bl.addWidget(t)
        bl.addStretch()
        x = QPushButton("✕")
        x.setFixedSize(36, 28)
        x.setFont(mono(False, 11))
        x.setCursor(Qt.PointingHandCursor)
        x.setStyleSheet(f"QPushButton {{ color:{DIM}; background:transparent; border:none; }} QPushButton:hover {{ color:{RED}; }}")
        x.clicked.connect(self.reject)
        bl.addWidget(x)
        lay.addWidget(bar)
        body = QWidget()
        body.setStyleSheet("background:#050f0a; border:1.5px solid #00ff88; border-top:none;")
        bl2 = QVBoxLayout(body)
        bl2.setContentsMargins(40, 24, 40, 24)
        bl2.setSpacing(12)
        dz = QLabel("Drag & drop files / folders here\nor")
        dz.setFont(mono(False, 11))
        dz.setStyleSheet(f"color:{DIM}; background:transparent; border:2px dashed {DARKB}; border-radius:4px; padding:26px;")
        dz.setAlignment(Qt.AlignCenter)
        bl2.addWidget(dz)
        br = QHBoxLayout()
        br.setSpacing(16)
        self.bf = QPushButton("Browse Files")
        self.bd = QPushButton("Browse Folder")
        for b in (self.bf, self.bd):
            b.setFixedHeight(38)
            b.setFont(mono(True, 10))
            b.setCursor(Qt.PointingHandCursor)
            b.setStyleSheet(
                f"""QPushButton {{ color:{NEON}; background:transparent; border:2px solid {NEON}; border-radius:4px; }}
                    QPushButton:hover {{ background:#0a1f14; }}"""
            )
            br.addWidget(b)
        bl2.addLayout(br)
        self.bf.clicked.connect(self.pick_files)
        self.bd.clicked.connect(self.pick_dir)
        self.sl = QLabel("Selected (0):")
        self.sl.setFont(mono(True, 10))
        self.sl.setStyleSheet(f"color:{DIM}; background:transparent; border:none;")
        bl2.addWidget(self.sl)
        self.listw = QWidget()
        self.listl = QVBoxLayout(self.listw)
        self.listl.setContentsMargins(0, 0, 0, 0)
        self.listl.setSpacing(6)
        sc = QScrollArea()
        sc.setWidgetResizable(True)
        sc.setStyleSheet("QScrollArea { background:transparent; border:none; }")
        sc.viewport().setStyleSheet("background:transparent;")
        sc.setWidget(self.listw)
        bl2.addWidget(sc, 1)
        fr = QHBoxLayout()
        cancel = QPushButton("Cancel")
        cancel.setFixedSize(140, 44)
        cancel.setFont(mono(True, 10))
        cancel.setCursor(Qt.PointingHandCursor)
        cancel.setStyleSheet(f"QPushButton {{ color:{DIM}; background:transparent; border:2px solid {DIM}; border-radius:4px; }}")
        cancel.clicked.connect(self.reject)
        fr.addWidget(cancel)
        fr.addStretch()
        self.lockbtn = NeonButton("Lock 0 Items")
        self.lockbtn.setFixedSize(220, 44)
        self.lockbtn.clicked.connect(self.accept)
        fr.addWidget(self.lockbtn)
        bl2.addLayout(fr)
        lay.addWidget(body, 1)
        self.setStyleSheet("QDialog { background:#050f0a; }")

    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dropEvent(self, e):
        for url in e.mimeData().urls():
            p = url.toLocalFile()
            if p and os.path.exists(p) and p not in self.paths:
                self.paths.append(p)
        self.refresh_list()

    def pick_files(self):
        ps, _ = QFileDialog.getOpenFileNames(self, "Select files to lock")
        for p in ps:
            if p not in self.paths:
                self.paths.append(p)
        self.refresh_list()

    def pick_dir(self):
        p = QFileDialog.getExistingDirectory(self, "Select folder to lock")
        if p and p not in self.paths:
            self.paths.append(p)
        self.refresh_list()

    def refresh_list(self):
        while self.listl.count():
            w = self.listl.takeAt(0).widget()
            if w:
                w.deleteLater()
        for p in self.paths:
            r = QWidget()
            rl = QHBoxLayout(r)
            rl.setContentsMargins(10, 6, 6, 6)
            n = QLabel(os.path.basename(p.rstrip(os.sep)) or p)
            n.setFont(mono(False, 10))
            n.setStyleSheet(f"color:{BRIGHT}; background:transparent; border:none;")
            rl.addWidget(n, 1)
            x = QPushButton("×")
            x.setFixedSize(28, 24)
            x.setFont(mono(True, 12))
            x.setCursor(Qt.PointingHandCursor)
            x.setStyleSheet(f"QPushButton {{ color:{RED}; background:transparent; border:none; }}")
            x.clicked.connect(lambda _=False, pp=p: (self.paths.remove(pp), self.refresh_list()))
            rl.addWidget(x)
            r.setStyleSheet(f"background:#04100a; border:1px solid {DARKB}; border-radius:4px;")
            self.listl.addWidget(r)
        self.sl.setText(f"Selected ({len(self.paths)}):")
        self.lockbtn.setText(f"Lock {len(self.paths)} Items")
        self.lockbtn.setEnabled(len(self.paths) > 0)


class SecCard(QFrame):
    def __init__(self, title, value, btn_text, red=False, parent=None):
        super().__init__(parent)
        self.setStyleSheet(
            f"""QFrame {{ background:#050f0a; border:2px solid {RED if red else NEON}; border-radius:6px; }}"""
        )
        lay = QHBoxLayout(self)
        lay.setContentsMargins(24, 14, 20, 14)
        tx = QVBoxLayout()
        tx.setSpacing(4)
        t = QLabel(title)
        t.setFont(mono(True, 10))
        t.setStyleSheet(f"color:{RED if red else NEON}; background:transparent; border:none;")
        tx.addWidget(t)
        v = QLabel(value)
        v.setFont(mono(False, 11))
        v.setStyleSheet(f"color:{DIM}; background:transparent; border:none;")
        tx.addWidget(v)
        self.val = v
        lay.addLayout(tx, 1)
        self.btn = QPushButton("→")
        self.btn.setFixedSize(52, 40)
        self.btn.setFont(mono(True, 16))
        self.btn.setCursor(Qt.PointingHandCursor)
        self.btn.setStyleSheet(
            f"""QPushButton {{ color:{RED if red else NEON}; background:transparent; border:none; }}
                QPushButton:hover {{ background:#0a1f14; border-radius:4px; }}"""
        )
        lay.addWidget(self.btn)
        if btn_text:
            self.btn.setText(btn_text)
            self.btn.setFont(mono(True, 10))
            self.btn.setFixedSize(110, 40)


class SettingsScreen(QWidget):
    nav_req = Signal(str)
    change_pw_req = Signal()
    recovery_req = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        main = QHBoxLayout()
        main.setContentsMargins(0, 0, 0, 0)
        main.setSpacing(0)
        self.sidebar = Sidebar("settings")
        self.sidebar.nav_req.connect(lambda k: self.nav_req.emit({"vault": "Vault", "log": "Activity Log", "settings": "Settings"}[k]))
        main.addWidget(self.sidebar)
        body = QWidget()
        bl = QVBoxLayout(body)
        bl.setContentsMargins(0, 0, 0, 0)
        bl.setSpacing(0)
        wrap = QHBoxLayout()
        wrap.addStretch()
        col = QWidget()
        col.setFixedWidth(560)
        cl = QVBoxLayout(col)
        cl.setContentsMargins(0, 26, 0, 0)
        cl.setSpacing(16)
        h = QLabel("> Settings")
        h.setFont(mono(True, 20))
        h.setStyleSheet(f"color:{BRIGHT}; background:transparent; border:none;")
        cl.addWidget(h)
        self.c_sec = SecCard("SECURITY", "Auto-lock · 5 min", "Edit")
        self._lock_opts = ["1 min", "5 min", "15 min", "30 min", "Never"]
        self._lock_i = 1
        self.c_sec.btn.clicked.connect(self.cycle_lock)
        cl.addWidget(self.c_sec)
        self.c_pw = SecCard("PASSWORD", "Change master password", "Change →")
        self.c_pw.btn.clicked.connect(lambda: self.change_pw_req.emit())
        cl.addWidget(self.c_pw)
        self.c_vault = SecCard("VAULT", "D:/SUMA/vault/", "Open")
        self.c_vault.btn.clicked.connect(self.open_vault)
        cl.addWidget(self.c_vault)
        self.c_rec = SecCard("RECOVERY", "Picture backup not set", "Create →")
        self.c_rec.btn.clicked.connect(lambda: self.recovery_req.emit())
        cl.addWidget(self.c_rec)
        cl.addStretch()
        dev = QLabel("Developed by MUNEEB UR REHMAN")
        dev.setFont(mono(False, 8))
        dev.setStyleSheet(f"color:{DIM}; background:transparent; border:none;")
        dev.setAlignment(Qt.AlignCenter)
        cl.addWidget(dev)
        wrap.addWidget(col)
        wrap.addStretch()
        bl.addLayout(wrap, 1)
        main.addWidget(body, 1)
        lay.addLayout(main, 1)

    def cycle_lock(self):
        self._lock_i = (self._lock_i + 1) % len(self._lock_opts)
        self.c_sec.val.setText(f"Auto-lock · {self._lock_opts[self._lock_i]}")
        win = self.window()
        if hasattr(win, "_autolock_min"):
            win._autolock_min = {"1 min": 1, "5 min": 5, "15 min": 15, "30 min": 30,
                                 "Never": None}[self._lock_opts[self._lock_i]]
            win._last_active = time.time()

    def refresh(self):
        _, cfg = find_config()
        if cfg and cfg.get("enc_key_rec"):
            self.c_rec.val.setText("Recovery picture set ✓")
            self.c_rec.btn.setText("Replace →")
        else:
            self.c_rec.val.setText("Picture backup not set")
            self.c_rec.btn.setText("Create →")

    def open_vault(self):
        os.makedirs(VAULT_DIR, exist_ok=True)
        try:
            if sys.platform.startswith("win"):
                os.startfile(VAULT_DIR)
            elif sys.platform == "darwin":
                os.system(f'open "{VAULT_DIR}"')
            else:
                os.system(f'xdg-open "{VAULT_DIR}"')
        except Exception:
            pass


class ChangePasswordScreen(QWidget):
    nav_req = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addStretch()
        wrap = QHBoxLayout()
        wrap.addStretch()
        card = Card(470, 600)
        cl = QVBoxLayout(card)
        cl.setContentsMargins(45, 32, 45, 28)
        cl.setSpacing(0)
        h = QLabel("> Change Master Password")
        h.setFont(mono(True, 17))
        h.setStyleSheet(f"color:{BRIGHT}; background:transparent; border:none;")
        h.setAlignment(Qt.AlignCenter)
        cl.addWidget(h)
        cl.addSpacing(20)
        self.cur = PasswordField("CURRENT PASSWORD")
        cl.addWidget(self.cur)
        cl.addSpacing(12)
        self.new1 = PasswordField("NEW MASTER PASSWORD")
        cl.addWidget(self.new1)
        cl.addSpacing(8)
        self.meter = StrengthMeter()
        cl.addWidget(self.meter)
        self.new1.edit.textChanged.connect(self.meter.set_strength)
        cl.addSpacing(6)
        self.new2 = PasswordField("CONFIRM NEW PASSWORD")
        cl.addWidget(self.new2)
        cl.addSpacing(6)
        gen = QPushButton("↻ generate strong password")
        gen.setFont(mono(False, 9))
        gen.setCursor(Qt.PointingHandCursor)
        gen.setFlat(True)
        gen.setStyleSheet(f"color:{DIM}; background:transparent; border:none; text-decoration:underline;")
        gen.clicked.connect(self.gen_pw)
        gl = QHBoxLayout()
        gl.addStretch()
        gl.addWidget(gen)
        gl.addStretch()
        cl.addLayout(gl)
        cl.addSpacing(2)
        self.err = QLabel("")
        self.err.setFont(mono(True, 9))
        self.err.setStyleSheet(f"color:{RED}; background:transparent; border:none;")
        self.err.setAlignment(Qt.AlignCenter)
        self.err.setFixedHeight(18)
        cl.addWidget(self.err)
        btn = NeonButton("Update Password")
        btn.setFixedWidth(380)
        bl = QHBoxLayout()
        bl.addStretch()
        bl.addWidget(btn)
        bl.addStretch()
        cl.addLayout(bl)
        btn.clicked.connect(self.submit)
        cl.addSpacing(8)
        back = QPushButton("< back to settings")
        back.setFont(mono(False, 9))
        back.setCursor(Qt.PointingHandCursor)
        back.setFlat(True)
        back.setStyleSheet(f"color:{DIM}; background:transparent; border:none;")
        back.clicked.connect(lambda: self.nav_req.emit("Settings"))
        bw = QHBoxLayout()
        bw.addStretch()
        bw.addWidget(back)
        bw.addStretch()
        cl.addLayout(bw)
        cl.addStretch()
        wrap.addWidget(card)
        wrap.addStretch()
        lay.addLayout(wrap)
        lay.addStretch()

    def gen_pw(self):
        p = gen_password()
        self.new1.edit.setText(p)
        self.new2.edit.setText(p)
        self.meter.set_strength(p)

    def submit(self):
        win = self.window()
        _, cfg = find_config()
        if not cfg or not verify_password(self.cur.text(), cfg["salt"], cfg["hash"]):
            self.err.setText("Current password is wrong.")
            return
        a, b = self.new1.text(), self.new2.text()
        if len(a) < 8:
            self.err.setText("New password must be at least 8 characters.")
            return
        if a != b:
            self.err.setText("New passwords do not match.")
            return
        dk = master_fernet(self.cur.text(), cfg["ksalt"]).decrypt(cfg["enc_key"].encode())
        ksalt = os.urandom(16).hex()
        salt, hh = hash_password(a)
        enc = master_fernet(a, ksalt).encrypt(dk).decode()
        cfg["salt"] = salt
        cfg["hash"] = hh
        cfg["ksalt"] = ksalt
        cfg["enc_key"] = enc
        save_config_to(win.cfg_path, cfg)
        for f_ in (self.cur, self.new1, self.new2):
            f_.clear()
        self.err.setText("")
        win.log.add("PASSWORD CHANGED", "master password updated")
        win.show_screen("settings")


class ActivityLogScreen(QWidget):
    nav_req = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        main = QHBoxLayout()
        main.setContentsMargins(0, 0, 0, 0)
        main.setSpacing(0)
        self.sidebar = Sidebar("log")
        self.sidebar.nav_req.connect(lambda k: self.nav_req.emit({"vault": "Vault", "log": "Activity Log", "settings": "Settings"}[k]))
        main.addWidget(self.sidebar)
        body = QWidget()
        bl = QVBoxLayout(body)
        bl.setContentsMargins(0, 0, 0, 0)
        bl.setSpacing(0)
        wrap = QHBoxLayout()
        wrap.addStretch()
        cw = 800
        card = Card(cw, 560)
        cl = QVBoxLayout(card)
        cl.setContentsMargins(50, 36, 50, 30)
        top = QHBoxLayout()
        h = QLabel("> Activity Log")
        h.setFont(mono(True, 18))
        h.setStyleSheet(f"color:{BRIGHT}; background:transparent; border:none;")
        top.addWidget(h)
        top.addStretch()
        clr = QPushButton("Clear Log")
        clr.setFixedSize(140, 34)
        clr.setFont(mono(True, 10))
        clr.setCursor(Qt.PointingHandCursor)
        clr.setStyleSheet(f"QPushButton {{ color:{DIM}; background:transparent; border:2px solid {DIM}; border-radius:4px; }}")
        clr.clicked.connect(self.clear_log)
        top.addWidget(clr)
        cl.addLayout(top)
        cl.addSpacing(10)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setStyleSheet("QScrollArea { background:transparent; border:none; }")
        self.scroll.viewport().setStyleSheet("background:transparent;")
        self.listw = QWidget()
        self.listl = QVBoxLayout(self.listw)
        self.listl.setContentsMargins(0, 0, 0, 0)
        self.listl.setSpacing(8)
        self.listl.addStretch()
        self.scroll.setWidget(self.listw)
        cl.addWidget(self.scroll, 1)
        wrap.addWidget(card)
        wrap.addStretch()
        bl.addLayout(wrap, 1)
        sp = QWidget()
        sp.setFixedHeight(24)
        bl.addWidget(sp)
        main.addWidget(body, 1)
        lay.addLayout(main, 1)

    def clear_log(self):
        self.window().log.clear()
        self.refresh()

    def refresh(self):
        while self.listl.count() > 1:
            w = self.listl.takeAt(0).widget()
            if w:
                w.deleteLater()
        for ev in self.window().log.events[-30:]:
            r = QWidget()
            rl = QHBoxLayout(r)
            rl.setContentsMargins(4, 6, 4, 6)
            t = QLabel(ev["time"])
            t.setFont(mono(False, 10))
            t.setStyleSheet(f"color:{DIM}; background:transparent; border:none;")
            t.setFixedWidth(90)
            rl.addWidget(t)
            col = RED if "FAIL" in ev["event"] else NEON
            pill = QLabel(ev["event"])
            pill.setFont(mono(True, 9))
            pill.setStyleSheet(
                f"color:{col}; background:transparent; border:2px solid {col}; border-radius:10px; padding:3px 10px;"
            )
            rl.addWidget(pill)
            dd = QLabel(ev["detail"])
            dd.setFont(mono(False, 10))
            dd.setStyleSheet(f"color:{BRIGHT}; background:transparent; border:none;")
            rl.addWidget(dd, 1)
            r.setStyleSheet(f"background:#04100a; border:1px solid {DARKB}; border-radius:4px;")
            self.listl.insertWidget(0, r)


class RecoverySetupScreen(QWidget):
    done = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.rec_key = None
        self.src = None
        self.saved = False
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addStretch()
        wrap = QHBoxLayout()
        wrap.addStretch()
        card = Card(560, 640)
        cl = QVBoxLayout(card)
        cl.setContentsMargins(45, 32, 45, 28)
        cl.setSpacing(0)
        h = QLabel("> Hide Your Recovery Key")
        h.setFont(mono(True, 18))
        h.setStyleSheet(f"color:{BRIGHT}; background:transparent; border:none;")
        h.setAlignment(Qt.AlignCenter)
        cl.addWidget(h)
        cl.addSpacing(10)
        for line in ["Pick any picture. SUMA hides a secret recovery key",
                     "inside it. Forget your password one day, and this",
                     "picture is the ONLY way back in. Keep it safe."]:
            s = QLabel(line)
            s.setFont(mono(False, 10))
            s.setStyleSheet(f"color:{DIM}; background:transparent; border:none;")
            s.setAlignment(Qt.AlignCenter)
            cl.addWidget(s)
        cl.addSpacing(14)
        self.preview = QLabel("No picture chosen")
        self.preview.setFixedSize(320, 170)
        self.preview.setAlignment(Qt.AlignCenter)
        self.preview.setFont(mono(False, 10))
        self.preview.setStyleSheet(
            f"color:{DIM}; background:#04100a; border:1.5px dashed {DARKB}; border-radius:4px;")
        pw = QHBoxLayout()
        pw.addStretch()
        pw.addWidget(self.preview)
        pw.addStretch()
        cl.addLayout(pw)
        cl.addSpacing(12)
        row = QHBoxLayout()
        row.setSpacing(12)
        browse = QPushButton("Choose Picture")
        browse.setFixedHeight(42)
        browse.setFont(mono(True, 10))
        browse.setCursor(Qt.PointingHandCursor)
        browse.setStyleSheet(
            f"""QPushButton {{ color:{NEON}; background:transparent; border:2px solid {NEON}; border-radius:4px; }}
                QPushButton:hover {{ background:#0a1f14; }}""")
        browse.clicked.connect(self.pick)
        row.addWidget(browse)
        self.save_btn = QPushButton("Save Recovery Picture")
        self.save_btn.setFixedHeight(42)
        self.save_btn.setFont(mono(True, 10))
        self.save_btn.setCursor(Qt.PointingHandCursor)
        self.save_btn.setEnabled(False)
        self.save_btn.setStyleSheet(
            f"""QPushButton {{ color:{NEON}; background:transparent; border:2px solid {NEON}; border-radius:4px; }}
                QPushButton:hover {{ background:#0a1f14; }}
                QPushButton:disabled {{ color:{DARKB}; border:2px solid {DARKB}; }}""")
        self.save_btn.clicked.connect(self.save_pic)
        row.addWidget(self.save_btn)
        cl.addLayout(row)
        cl.addSpacing(8)
        self.status = QLabel("")
        self.status.setFont(mono(True, 10))
        self.status.setStyleSheet(f"color:{NEON}; background:transparent; border:none;")
        self.status.setAlignment(Qt.AlignCenter)
        self.status.setWordWrap(True)
        cl.addWidget(self.status)
        cl.addSpacing(10)
        cont = NeonButton("Continue  →")
        cont.setFixedWidth(380)
        bl = QHBoxLayout()
        bl.addStretch()
        bl.addWidget(cont)
        bl.addStretch()
        cl.addLayout(bl)
        cont.clicked.connect(self.finish)
        cl.addSpacing(6)
        sk = QPushButton("skip for now")
        sk.setFont(mono(False, 9))
        sk.setCursor(Qt.PointingHandCursor)
        sk.setFlat(True)
        sk.setStyleSheet(f"color:{DIM}; background:transparent; border:none; text-decoration:underline;")
        sk.clicked.connect(self.skip)
        sl = QHBoxLayout()
        sl.addStretch()
        sl.addWidget(sk)
        sl.addStretch()
        cl.addLayout(sl)
        cl.addStretch()
        wrap.addWidget(card)
        wrap.addStretch()
        lay.addLayout(wrap)
        lay.addStretch()

    def set_rec_key(self, key):
        self.rec_key = key
        self.saved = False
        self.src = None
        self.preview.setText("No picture chosen")
        self.preview.setPixmap(QPixmap())
        self.preview.setStyleSheet(
            f"color:{DIM}; background:#04100a; border:1.5px dashed {DARKB}; border-radius:4px;")
        self.save_btn.setEnabled(False)
        self.status.setText("")

    def pick(self):
        p, _ = QFileDialog.getOpenFileName(self, "Choose a picture", "",
                                           "Images (*.png *.jpg *.jpeg *.bmp *.webp)")
        if p:
            self.src = p
            pm = QPixmap(p)
            if not pm.isNull():
                self.preview.setPixmap(pm.scaled(300, 150, Qt.KeepAspectRatio, Qt.SmoothTransformation))
                self.preview.setStyleSheet(
                    f"background:#04100a; border:1.5px solid {NEON}; border-radius:4px;")
            self.save_btn.setEnabled(True)

    def save_pic(self):
        if not self.src or not self.rec_key:
            return
        dest, _ = QFileDialog.getSaveFileName(self, "Save recovery picture",
                                              "suma-recovery.png", "PNG (*.png)")
        if not dest:
            return
        if not dest.lower().endswith(".png"):
            dest += ".png"
        try:
            im = stego_hide(self.src, self.rec_key)
            if not im.save(dest, "PNG"):
                raise IOError("Could not save the picture.")
            self.saved = True
            self.status.setStyleSheet(f"color:{NEON}; background:transparent; border:none;")
            self.status.setText("✓ Key hidden inside the picture. Keep it safe!")
        except Exception as ex:
            self.status.setStyleSheet(f"color:{RED}; background:transparent; border:none;")
            self.status.setText(str(ex))

    def finish(self):
        self.done.emit()

    def skip(self):
        if confirm_box(self, "> Skip recovery key?",
                       "Are you sure you don't want to keep the recovery key?\n"
                       "This is the only way back in if you forget your password."):
            self.done.emit()
        else:
            self.status.setStyleSheet(f"color:{NEON}; background:transparent; border:none;")
            self.status.setText("Please choose a picture to hide your recovery key.")
            self.pick()


class RecoverScreen(QWidget):
    recovered = Signal(bytes)
    back_req = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addStretch()
        wrap = QHBoxLayout()
        wrap.addStretch()
        card = Card(560, 520)
        cl = QVBoxLayout(card)
        cl.setContentsMargins(45, 32, 45, 28)
        cl.setSpacing(0)
        h = QLabel("> Recover with Picture")
        h.setFont(mono(True, 18))
        h.setStyleSheet(f"color:{BRIGHT}; background:transparent; border:none;")
        h.setAlignment(Qt.AlignCenter)
        cl.addWidget(h)
        cl.addSpacing(10)
        for line in ["Drop your recovery picture here, or browse for it.",
                     "SUMA will find the hidden key inside."]:
            s = QLabel(line)
            s.setFont(mono(False, 10))
            s.setStyleSheet(f"color:{DIM}; background:transparent; border:none;")
            s.setAlignment(Qt.AlignCenter)
            cl.addWidget(s)
        cl.addSpacing(14)
        self.drop = QLabel("Drop picture here\nor")
        self.drop.setFixedSize(360, 130)
        self.drop.setAlignment(Qt.AlignCenter)
        self.drop.setFont(mono(False, 11))
        self.drop.setStyleSheet(
            f"color:{DIM}; background:transparent; border:2px dashed {DARKB}; border-radius:4px;")
        dw = QHBoxLayout()
        dw.addStretch()
        dw.addWidget(self.drop)
        dw.addStretch()
        cl.addLayout(dw)
        cl.addSpacing(10)
        browse = QPushButton("Browse Picture")
        browse.setFixedSize(220, 42)
        browse.setFont(mono(True, 10))
        browse.setCursor(Qt.PointingHandCursor)
        browse.setStyleSheet(
            f"""QPushButton {{ color:{NEON}; background:transparent; border:2px solid {NEON}; border-radius:4px; }}
                QPushButton:hover {{ background:#0a1f14; }}""")
        browse.clicked.connect(self.pick)
        bw = QHBoxLayout()
        bw.addStretch()
        bw.addWidget(browse)
        bw.addStretch()
        cl.addLayout(bw)
        cl.addSpacing(8)
        self.err = QLabel("")
        self.err.setFont(mono(True, 10))
        self.err.setStyleSheet(f"color:{RED}; background:transparent; border:none;")
        self.err.setAlignment(Qt.AlignCenter)
        self.err.setWordWrap(True)
        cl.addWidget(self.err)
        cl.addSpacing(8)
        back = QPushButton("< back to unlock")
        back.setFont(mono(False, 9))
        back.setCursor(Qt.PointingHandCursor)
        back.setFlat(True)
        back.setStyleSheet(f"color:{DIM}; background:transparent; border:none;")
        back.clicked.connect(lambda: self.back_req.emit())
        bw2 = QHBoxLayout()
        bw2.addStretch()
        bw2.addWidget(back)
        bw2.addStretch()
        cl.addLayout(bw2)
        cl.addStretch()
        wrap.addWidget(card)
        wrap.addStretch()
        lay.addLayout(wrap)
        lay.addStretch()

    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dropEvent(self, e):
        urls = e.mimeData().urls()
        if urls:
            self.try_picture(urls[0].toLocalFile())

    def pick(self):
        p, _ = QFileDialog.getOpenFileName(self, "Choose recovery picture", "",
                                           "Images (*.png *.jpg *.jpeg *.bmp *.webp)")
        if p:
            self.try_picture(p)

    def try_picture(self, p):
        self.err.setText("")
        _, cfg = find_config()
        if not cfg or "enc_key_rec" not in cfg:
            self.err.setText("This vault has no recovery picture set up.")
            return
        try:
            key = stego_extract(p)
        except Exception:
            key = None
        if not key:
            self.err.setText("No recovery key found in this picture.")
            return
        try:
            dk = rec_fernet(key, cfg["rec_salt"]).decrypt(cfg["enc_key_rec"].encode())
        except Exception:
            self.err.setText("Invalid recovery picture.")
            return
        self.recovered.emit(dk)


class ResetPasswordScreen(QWidget):
    reset_done = Signal(bytes)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._dk = None
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addStretch()
        wrap = QHBoxLayout()
        wrap.addStretch()
        card = Card(470, 560)
        cl = QVBoxLayout(card)
        cl.setContentsMargins(45, 32, 45, 28)
        cl.setSpacing(0)
        h = QLabel("> Set New Master Password")
        h.setFont(mono(True, 17))
        h.setStyleSheet(f"color:{BRIGHT}; background:transparent; border:none;")
        h.setAlignment(Qt.AlignCenter)
        cl.addWidget(h)
        cl.addSpacing(8)
        s = QLabel("Recovery accepted. Choose a new master password.")
        s.setFont(mono(False, 10))
        s.setStyleSheet(f"color:{DIM}; background:transparent; border:none;")
        s.setAlignment(Qt.AlignCenter)
        cl.addWidget(s)
        cl.addSpacing(18)
        self.new1 = PasswordField("NEW MASTER PASSWORD")
        cl.addWidget(self.new1)
        cl.addSpacing(8)
        self.meter = StrengthMeter()
        cl.addWidget(self.meter)
        self.new1.edit.textChanged.connect(self.meter.set_strength)
        cl.addSpacing(6)
        self.new2 = PasswordField("CONFIRM NEW PASSWORD")
        cl.addWidget(self.new2)
        cl.addSpacing(6)
        gen = QPushButton("↻ generate strong password")
        gen.setFont(mono(False, 9))
        gen.setCursor(Qt.PointingHandCursor)
        gen.setFlat(True)
        gen.setStyleSheet(f"color:{DIM}; background:transparent; border:none; text-decoration:underline;")
        gen.clicked.connect(self.gen_pw)
        gl = QHBoxLayout()
        gl.addStretch()
        gl.addWidget(gen)
        gl.addStretch()
        cl.addLayout(gl)
        cl.addSpacing(2)
        self.err = QLabel("")
        self.err.setFont(mono(True, 9))
        self.err.setStyleSheet(f"color:{RED}; background:transparent; border:none;")
        self.err.setAlignment(Qt.AlignCenter)
        self.err.setFixedHeight(18)
        cl.addWidget(self.err)
        btn = NeonButton("Set New Password")
        btn.setFixedWidth(380)
        bl = QHBoxLayout()
        bl.addStretch()
        bl.addWidget(btn)
        bl.addStretch()
        cl.addLayout(bl)
        btn.clicked.connect(self.submit)
        cl.addStretch()
        wrap.addWidget(card)
        wrap.addStretch()
        lay.addLayout(wrap)
        lay.addStretch()

    def set_dk(self, dk):
        self._dk = dk
        self.new1.clear()
        self.new2.clear()
        self.err.setText("")

    def gen_pw(self):
        p = gen_password()
        self.new1.edit.setText(p)
        self.new2.edit.setText(p)
        self.meter.set_strength(p)

    def submit(self):
        a, b = self.new1.text(), self.new2.text()
        if len(a) < 8:
            self.err.setText("Password must be at least 8 characters.")
            return
        if a != b:
            self.err.setText("Passwords do not match.")
            return
        win = self.window()
        _, cfg = find_config()
        ksalt = os.urandom(16).hex()
        salt, hh = hash_password(a)
        enc = master_fernet(a, ksalt).encrypt(self._dk).decode()
        cfg["salt"] = salt
        cfg["hash"] = hh
        cfg["ksalt"] = ksalt
        cfg["enc_key"] = enc
        save_config_to(win.cfg_path, cfg)
        self.reset_done.emit(self._dk)


class MainWindow(QMainWindow):
    def __init__(self, icon_pm):
        super().__init__()
        self.setWindowFlags(Qt.FramelessWindowHint)
        self.resize(1100, 700)
        if icon_pm and not icon_pm.isNull():
            self.setWindowIcon(QIcon(icon_pm))
        self.icon_pm = icon_pm
        self.engine = None
        self.log = ActivityLog()
        back = BackPanel()
        self.setCentralWidget(back)
        lay = QVBoxLayout(back)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        self.titlebar = TitleBar(self, icon_pm)
        lay.addWidget(self.titlebar)
        self.stack = QStackedWidget()
        lay.addWidget(self.stack, 1)
        self.setup = SetupScreen(icon_pm)
        self.setup.password_set.connect(self.on_password_set)
        self.unlock = UnlockScreen(icon_pm)
        self.unlock.unlocked.connect(self.on_unlocked)
        self.unlock.forgot_req.connect(lambda: self.show_screen("recover"))
        self.dash = DashboardScreen()
        self.dash.add_req.connect(self.open_add)
        self.dash.nav_req.connect(self.nav)
        self.dash.sidebar.lock_req.connect(self.lock_vault)
        self.settings = SettingsScreen()
        self.settings.nav_req.connect(self.nav)
        self.settings.change_pw_req.connect(lambda: self.show_screen("chpw"))
        self.settings.recovery_req.connect(self.setup_recovery)
        self.settings.sidebar.lock_req.connect(self.lock_vault)
        self.chpw = ChangePasswordScreen()
        self.chpw.nav_req.connect(self.nav)
        self.logscr = ActivityLogScreen()
        self.logscr.nav_req.connect(self.nav)
        self.logscr.sidebar.lock_req.connect(self.lock_vault)
        self.recovery = RecoverySetupScreen()
        self.recovery.done.connect(self.on_recovery_done)
        self.recoverscr = RecoverScreen()
        self.recoverscr.recovered.connect(self.on_recovered)
        self.recoverscr.back_req.connect(lambda: self.show_screen("unlock"))
        self.resetpw = ResetPasswordScreen()
        self.resetpw.reset_done.connect(self.on_reset_done)
        for w in [self.setup, self.unlock, self.dash, self.settings, self.chpw,
                  self.logscr, self.recovery, self.recoverscr, self.resetpw]:
            self.stack.addWidget(w)
        self.cfg_path, cfg = find_config()
        self._rec_return = "dash"
        if cfg:
            print("config found")
        else:
            print("no config - showing setup")
        self._rdrag = None
        self._cur = None
        self.setMouseTracking(True)
        for wdg in self.findChildren(QWidget):
            wdg.setMouseTracking(True)
        QApplication.instance().installEventFilter(self)
        self._last_active = time.time()
        self._autolock_min = 5
        self._autolock_timer = QTimer(self)
        self._autolock_timer.timeout.connect(self._check_autolock)
        self._autolock_timer.start(15000)
        self._shortcut = QShortcut(QKeySequence("Ctrl+Shift+L"), self)
        self._shortcut.setContext(Qt.ApplicationShortcut)
        self._shortcut.activated.connect(self._hotkey_lock)
        self.tray = QSystemTrayIcon(self)
        self.tray.setIcon(self._tray_icon(icon_pm))
        self.tray.setToolTip("SUMA — vault locked")
        tmenu = QMenu()
        tmenu.addAction("Open SUMA", self._tray_show)
        tmenu.addAction("Lock Vault", self.lock_vault)
        tmenu.addSeparator()
        tmenu.addAction("Quit", QApplication.instance().quit)
        self.tray.setContextMenu(tmenu)
        self.tray.activated.connect(self._tray_activated)
        if QSystemTrayIcon.isSystemTrayAvailable():
            self.tray.show()
        self._fade = None
        self.show_screen("unlock" if cfg else "setup")
        qr = self.frameGeometry()
        cp = QApplication.primaryScreen().availableGeometry().center()
        qr.moveCenter(cp)
        self.move(qr.topLeft())

    def show_screen(self, name):
        m = {"setup": self.setup, "unlock": self.unlock, "dash": self.dash,
             "settings": self.settings, "chpw": self.chpw, "log": self.logscr,
             "recovery": self.recovery, "recover": self.recoverscr, "resetpw": self.resetpw}
        w = m[name]
        mins = {"setup": (960, 700), "unlock": (960, 620), "dash": (1000, 430),
                "settings": (1000, 480), "chpw": (960, 680), "log": (1000, 640),
                "recovery": (960, 720), "recover": (960, 620), "resetpw": (960, 660)}
        self.setMinimumSize(*mins[name])
        if name == "dash":
            self.dash.refresh()
        if name == "log":
            self.logscr.refresh()
        if name == "settings":
            self.settings.refresh()
        self.stack.setCurrentWidget(w)
        eff = QGraphicsOpacityEffect(self.stack)
        self.stack.setGraphicsEffect(eff)
        self._fade = QPropertyAnimation(eff, b"opacity")
        self._fade.setDuration(180)
        self._fade.setStartValue(0.0)
        self._fade.setEndValue(1.0)
        self._fade.start()
        for scr in (self.dash, self.settings, self.logscr):
            scr.sidebar.refresh_profile()
        if name == "unlock":
            self.unlock.pw.edit.setFocus()
        elif name == "setup":
            self.setup.pw1.edit.setFocus()

    def on_recovery_done(self):
        self.show_screen(self._rec_return)

    def on_recovered(self, dk):
        self._pending_dk = dk
        self.resetpw.set_dk(dk)
        self.show_screen("resetpw")

    def on_reset_done(self, dk):
        self.engine = VaultEngine(dk)
        self._last_active = time.time()
        self.tray.setToolTip("SUMA — vault unlocked")
        self.log.add("PASSWORD RECOVERED", "master password reset via recovery picture")
        self.show_screen("dash")

    def setup_recovery(self):
        if not self.engine:
            return
        _, cfg = find_config()
        if not cfg:
            return
        if cfg.get("enc_key_rec"):
            if not confirm_box(self, "> Replace recovery picture?",
                               "The old recovery picture will stop working."):
                return
        rec_key = os.urandom(32)
        rec_salt = os.urandom(16).hex()
        cfg["rec_salt"] = rec_salt
        cfg["enc_key_rec"] = rec_fernet(rec_key, rec_salt).encrypt(self.engine.key).decode()
        save_config_to(self.cfg_path, cfg)
        self.recovery.set_rec_key(rec_key)
        self._rec_return = "settings"
        self.log.add("RECOVERY SET", "recovery picture created")
        self.show_screen("recovery")

    def nav(self, tab):
        self.show_screen({"Vault": "dash", "Activity Log": "log", "Settings": "settings"}[tab])

    def lock_vault(self):
        if self.engine is None:
            return
        self.log.add("VAULT LOCKED", "vault locked by user")
        self.engine = None
        self.unlock.pw.clear()
        self.tray.setToolTip("SUMA — vault locked")
        self.show_screen("unlock")

    def _check_autolock(self):
        if self.engine is None or self._autolock_min is None:
            return
        if time.time() - self._last_active >= self._autolock_min * 60:
            self.log.add("AUTO-LOCK", f"vault locked after {self._autolock_min} min idle")
            self.engine = None
            self.unlock.pw.clear()
            self.tray.setToolTip("SUMA — vault locked")
            self.show_screen("unlock")

    def _hotkey_lock(self):
        if self.engine is not None:
            self.log.add("VAULT LOCKED", "locked via Ctrl+Shift+L")
            self.lock_vault()

    def _tray_icon(self, icon_pm):
        if icon_pm and not icon_pm.isNull():
            return QIcon(icon_pm)
        pm = QPixmap(64, 64)
        pm.fill(Qt.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(QPen(QColor(NEON), 5))
        p.setBrush(Qt.NoBrush)
        p.drawRoundedRect(14, 28, 36, 26, 4, 4)
        p.drawArc(20, 14, 24, 24, 0, 180 * 16)
        p.end()
        return QIcon(pm)

    def _tray_activated(self, reason):
        if reason in (QSystemTrayIcon.Trigger, QSystemTrayIcon.DoubleClick):
            self._tray_show()

    def _tray_show(self):
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def changeEvent(self, e):
        if e.type() == QEvent.WindowStateChange and self.isMinimized():
            self.hide()
            self.tray.showMessage("SUMA", "Vault keeps running in the tray.",
                                  QSystemTrayIcon.Information, 2000)
        super().changeEvent(e)

    def _edge_dir(self, gp):
        if self.isMaximized():
            return None
        g = self.frameGeometry()
        m = RESIZE_M
        l = abs(gp.x() - g.x()) <= m
        r = abs(gp.x() - (g.x() + g.width())) <= m
        t = abs(gp.y() - g.y()) <= m
        b = abs(gp.y() - (g.y() + g.height())) <= m
        if t and l:
            return "tl"
        if t and r:
            return "tr"
        if b and l:
            return "bl"
        if b and r:
            return "br"
        if l:
            return "l"
        if r:
            return "r"
        if t:
            return "t"
        if b:
            return "b"
        return None

    def _edge_cursor(self, d):
        return {"l": Qt.SizeHorCursor, "r": Qt.SizeHorCursor,
                "t": Qt.SizeVerCursor, "b": Qt.SizeVerCursor,
                "tl": Qt.SizeFDiagCursor, "br": Qt.SizeFDiagCursor,
                "tr": Qt.SizeBDiagCursor, "bl": Qt.SizeBDiagCursor}[d]

    def _apply_resize(self, gp):
        d, start, geo = self._rdrag
        dx = gp.x() - start.x()
        dy = gp.y() - start.y()
        x, y, w, h = geo.x(), geo.y(), geo.width(), geo.height()
        mw, mh = self.minimumWidth(), self.minimumHeight()
        if "l" in d:
            nw = max(mw, w - dx)
            x += w - nw
            w = nw
        if "r" in d:
            w = max(mw, w + dx)
        if "t" in d:
            nh = max(mh, h - dy)
            y += h - nh
            h = nh
        if "b" in d:
            h = max(mh, h + dy)
        self.setGeometry(x, y, w, h)

    def eventFilter(self, obj, ev):
        t = ev.type()
        if t in (QEvent.MouseButtonPress, QEvent.KeyPress, QEvent.Wheel):
            self._last_active = time.time()
        if t == QEvent.MouseMove:
            if self._rdrag:
                self._apply_resize(ev.globalPosition().toPoint())
                return True
            if ev.buttons() == Qt.NoButton:
                d = self._edge_dir(ev.globalPosition().toPoint())
                cur = None
                if d and not isinstance(obj, (QPushButton, QLineEdit)):
                    cur = self._edge_cursor(d)
                if cur != self._cur:
                    self._cur = cur
                    if cur is not None:
                        self.setCursor(cur)
                    else:
                        self.unsetCursor()
        elif t == QEvent.MouseButtonPress:
            if ev.button() == Qt.LeftButton and not self.isMaximized():
                d = self._edge_dir(ev.globalPosition().toPoint())
                if d and not isinstance(obj, (QPushButton, QLineEdit)):
                    self._rdrag = (d, ev.globalPosition().toPoint(), self.frameGeometry())
                    self._cur = self._edge_cursor(d)
                    self.setCursor(self._cur)
                    return True
        elif t == QEvent.MouseButtonRelease:
            if self._rdrag and ev.button() == Qt.LeftButton:
                self._rdrag = None
                self._cur = None
                self.unsetCursor()
                return True
        return False

    def on_password_set(self, dk, rec_key):
        self.engine = VaultEngine(dk)
        self._last_active = time.time()
        self.tray.setToolTip("SUMA — vault unlocked")
        self.cfg_path, _ = find_config()
        self.recovery.set_rec_key(rec_key)
        self._rec_return = "dash"
        self.log.add("VAULT CREATED", "master password set")
        self.show_screen("recovery")

    def on_unlocked(self, dk):
        self.engine = VaultEngine(dk)
        self._last_active = time.time()
        self.tray.setToolTip("SUMA — vault unlocked")
        self.log.add("VAULT UNLOCKED", "master password accepted")
        self.show_screen("dash")

    def open_add(self):
        dlg = AddDialog(self)
        if dlg.exec() and dlg.paths:
            n = len(dlg.paths)
            if not confirm_box(self, "> Lock items?",
                               f"{n} item{'s' if n != 1 else ''} will be encrypted and moved into the vault."):
                return
            for p in dlg.paths:
                try:
                    name = self.engine.lock(p)
                    self.log.add("LOCKED", name)
                except Exception as ex:
                    self.log.add("LOCK FAILED", f"{os.path.basename(p)}: {ex}")
            self.dash.refresh()

    def unlock_item(self, vid):
        item = next((m for m in self.engine.manifest if m["id"] == vid), None)
        if not item:
            return
        if not confirm_box(self, "> Unlock item?",
                           f"'{item['name']}' will be decrypted back to its original location."):
            return
        try:
            name = self.engine.unlock(vid)
            self.log.add("UNLOCKED", name or vid)
        except Exception as ex:
            self.log.add("UNLOCK FAILED", str(ex))
        self.dash.refresh()

    def remove_item(self, vid):
        if ask_password(self) is None:
            return
        item = next((m for m in self.engine.manifest if m["id"] == vid), None)
        if not item:
            return
        if not confirm_box(self, "> Remove forever?",
                           f"Do you really want to remove '{item['name']}'?\nThere is no way to recover it after deletion."):
            return
        name = self.engine.remove(vid)
        self.log.add("REMOVED", f"{name} permanently deleted")
        self.dash.refresh()


def make_splash(icon_pm):
    w, h = 520, 360
    pm = QPixmap(w, h)
    pm.fill(QColor("#020604"))
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    pen = QPen(QColor(0, 255, 136, 14))
    pen.setWidth(1)
    p.setPen(pen)
    for x in range(0, w, 40):
        p.drawLine(x, 0, x, h)
    for y in range(0, h, 40):
        p.drawLine(0, y, w, h)
    rg = QRadialGradient(w / 2, h / 2 - 20, 210)
    rg.setColorAt(0, QColor(0, 255, 136, 46))
    rg.setColorAt(1, QColor(0, 255, 136, 0))
    p.fillRect(0, 0, w, h, QBrush(rg))
    if icon_pm and not icon_pm.isNull():
        lp = icon_pm.scaled(96, 96, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        p.drawPixmap((w - 96) // 2, 52, lp)
    p.setPen(QColor(BRIGHT))
    p.setFont(mono(True, 34))
    p.drawText(0, 168, w, 50, Qt.AlignCenter, "SUMA")
    p.setPen(QColor(DIM))
    p.setFont(mono(False, 11))
    p.drawText(0, 214, w, 30, Qt.AlignCenter, "YOUR FILES. YOUR RULES.")
    p.setPen(QColor(DARKB))
    p.setFont(mono(False, 9))
    p.drawText(0, h - 66, w, 20, Qt.AlignCenter, "by MUNEEB UR REHMAN")
    p.end()
    return QSplashScreen(pm)


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("SUMA")
    try:
        from cryptography.fernet import Fernet
    except ImportError:
        QMessageBox.critical(None, "SUMA",
                             "Missing package: cryptography\n\nRun in terminal:\n pip install PySide6 cryptography")
        sys.exit(1)
    icon_pm = find_icon()
    if icon_pm.isNull():
        print("icon not found at", ICON_PATHS)
    else:
        print("icon loaded")
    if not icon_pm.isNull():
        app.setWindowIcon(QIcon(icon_pm))
    splash = make_splash(icon_pm)
    splash.show()
    app.processEvents()
    win = MainWindow(icon_pm)
    dots = {"n": 0}

    def tick():
        dots["n"] = (dots["n"] + 1) % 4
        splash.showMessage("initializing secure vault" + "." * dots["n"],
                           Qt.AlignBottom | Qt.AlignCenter, QColor(NEON))

    timer = QTimer()
    timer.timeout.connect(tick)
    timer.start(400)
    tick()

    def reveal():
        timer.stop()
        splash.finish(win)
        win.show()
        win.raise_()
        win.activateWindow()

    QTimer.singleShot(2200, reveal)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
