import os
import time
import sys
import json
import math
import shutil
import tempfile
import zipfile
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
from config import find_config, save_config, save_config_to, save_profile_pic
from crypto import hash_password, master_fernet, needs_upgrade, rec_fernet, upgrade_hash, verify_password
from stego import stego_extract, stego_hide
from ui_widgets import Sidebar, AvatarWidget, BRIGHT, Card, CatCard, DARKB, DIM, FileRow, NEON, NameField, NeonButton, PasswordField, RED, SecCard, StrengthMeter, confirm_box, mono
from utils import CAT_COLORS, CAT_ORDER, fmt_size, gen_password


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
        salt, vsalt, hh, it = hash_password(a)
        ksalt = os.urandom(16).hex()
        dk = os.urandom(32)
        enc = master_fernet(a, ksalt).encrypt(dk).decode()
        rec_key = os.urandom(32)
        rec_salt = os.urandom(16).hex()
        enc_rec = rec_fernet(rec_key, rec_salt).encrypt(dk).decode()
        save_config({"ver": 2, "salt": salt, "ver_salt": vsalt, "hash": hh, "iter": it,
                     "ksalt": ksalt, "enc_key": enc,
                     "rec_salt": rec_salt, "enc_key_rec": enc_rec, "rec_verified": False,
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
        if verify_password(self.pw.text(), cfg):
            dk = master_fernet(self.pw.text(), cfg["ksalt"]).decrypt(cfg["enc_key"].encode())
            if needs_upgrade(cfg):
                upgrade_hash(cfg, self.pw.text())
                save_config_to(self.window().cfg_path, cfg)
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
        valid = [m for m in win.engine.manifest
                 if isinstance(m, dict) and m.get("id") and m.get("name")]
        for m in valid:
            counts[m.get("cat", "?")] = counts.get(m.get("cat", "?"), 0) + 1
            sizes[m.get("cat", "?")] = sizes.get(m.get("cat", "?"), 0) + m.get("size", 0)
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
        items = [m for m in valid if m.get("cat") == self.cat]
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
        total = len(valid)
        self.stat.setText(f"vault secured  ·  {total} items locked")


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
            if cfg.get("rec_verified"):
                self.c_rec.val.setText("Recovery picture verified ✓")
            else:
                self.c_rec.val.setText("Recovery key not finished — recreate")
            self.c_rec.btn.setText("Replace →")
        else:
            self.c_rec.val.setText("Picture backup not set")
            self.c_rec.btn.setText("Create →")

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
        if not cfg or not verify_password(self.cur.text(), cfg):
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
        salt, vsalt, hh, it = hash_password(a)
        enc = master_fernet(a, ksalt).encrypt(dk).decode()
        cfg["ver"] = 2
        cfg["salt"] = salt
        cfg["ver_salt"] = vsalt
        cfg["hash"] = hh
        cfg["iter"] = it
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
        log = self.window().log
        items = log.items if hasattr(log, "items") else []
        for ev in items[-30:]:
            r = QWidget()
            rl = QHBoxLayout(r)
            rl.setContentsMargins(4, 6, 4, 6)
            t = QLabel(ev.get("at", ""))
            t.setFont(mono(False, 10))
            t.setStyleSheet(f"color:{DIM}; background:transparent; border:none;")
            t.setFixedWidth(90)
            rl.addWidget(t)
            action = ev.get("action", "")
            col = RED if "FAIL" in action else NEON
            pill = QLabel(action)
            pill.setFont(mono(True, 9))
            pill.setStyleSheet(
                f"color:{col}; background:transparent; border:2px solid {col}; border-radius:10px; padding:3px 10px;"
            )
            rl.addWidget(pill)
            dd = QLabel(ev.get("detail", ""))
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
        self._on_verified = None
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

    def set_on_verified(self, fn):
        self._on_verified = fn

    def set_rec_key(self, key):
        self.rec_key = key
        self._on_verified = None
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
            back = stego_extract(dest)
            if back is None or bytes(back) != bytes(self.rec_key):
                raise IOError("Verification failed: key could not be read back from the saved picture.")
            self.saved = True
            self.status.setStyleSheet(f"color:{NEON}; background:transparent; border:none;")
            self.status.setText("✓ Key hidden inside the picture. Keep it safe!")
            if self._on_verified:
                self._on_verified()
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
        salt, vsalt, hh, it = hash_password(a)
        enc = master_fernet(a, ksalt).encrypt(self._dk).decode()
        cfg["ver"] = 2
        cfg["salt"] = salt
        cfg["ver_salt"] = vsalt
        cfg["hash"] = hh
        cfg["iter"] = it
        cfg["ksalt"] = ksalt
        cfg["enc_key"] = enc
        save_config_to(win.cfg_path, cfg)
        self.reset_done.emit(self._dk)


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
        if cfg and verify_password(self.field.text(), cfg):
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
