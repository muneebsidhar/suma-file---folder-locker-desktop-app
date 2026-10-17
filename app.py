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
from config import startup_config, find_config, load_avatar_pm, profile_path, save_config_to, save_profile_pic
from crypto import rec_fernet
from screens import (ActivityLogScreen, AddDialog, ask_password, ChangePasswordScreen,
    DashboardScreen, RecoverScreen, RecoverySetupScreen, ResetPasswordScreen,
    SettingsScreen, SetupScreen, UnlockScreen)
from ui_widgets import AvatarWidget, BRIGHT, BackPanel, DARKB, DIM, NEON, RESIZE_M, confirm_box, mono
from vault import ActivityLog, ManifestCorruptError, VaultEngine


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
        self._pending_rec = None
        self.cfg_path, cfg, migrated = startup_config()
        self._rec_return = "dash"
        if migrated:
            print("vault migrated to", self.cfg_path)
        elif cfg:
            print("config found")
        else:
            print("no config - showing setup")
        self._migrated = migrated
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
        if getattr(self, "_migrated", False):
            QTimer.singleShot(600, self._show_migrated)
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
        enc_rec = rec_fernet(rec_key, rec_salt).encrypt(self.engine.key).decode()
        self._pending_rec = (rec_salt, enc_rec)

        def commit():
            _, c2 = find_config()
            if not c2:
                return
            c2["rec_salt"] = self._pending_rec[0]
            c2["enc_key_rec"] = self._pending_rec[1]
            c2["rec_verified"] = True
            save_config_to(self.cfg_path, c2)
            self._pending_rec = None
            self.log.add("RECOVERY SET", "recovery picture verified and saved")

        self.recovery.set_rec_key(rec_key)
        self.recovery.set_on_verified(commit)
        self._rec_return = "settings"
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

    def _show_migrated(self):
        QMessageBox.information(self, "SUMA",
                                "Your vault was moved to a safer location:\n\n"
                                f"{self.cfg_path}\n\n"
                                "Your files, password and settings are unchanged.")

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
        self.recovery.set_on_verified(self._mark_rec_verified)
        self._rec_return = "dash"
        self.log.add("VAULT CREATED", "master password set")
        self.show_screen("recovery")

    def _mark_rec_verified(self):
        _, cfg = find_config()
        if cfg:
            cfg["rec_verified"] = True
            save_config_to(self.cfg_path, cfg)
            self.log.add("RECOVERY SET", "recovery picture verified and saved")

    def on_unlocked(self, dk):
        try:
            self.engine = VaultEngine(dk)
        except ManifestCorruptError as ex:
            QMessageBox.critical(self, "SUMA",
                                 "Vault metadata is damaged and cannot be read safely:\n\n"
                                 f"{ex}\n\nYour encrypted files were NOT touched. "
                                 "Restore manifest.json from a backup before continuing.")
            self.log.add("MANIFEST CORRUPT", str(ex))
            return
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
                    res = self.engine.lock(p)
                    self.log.add("LOCKED", res["name"])
                    if res.get("warning"):
                        self.log.add("LOCK WARNING", res["warning"])
                        QMessageBox.warning(self, "SUMA",
                                            "Item encrypted and stored, but:\n\n" + res["warning"])
                except Exception as ex:
                    self.log.add("LOCK FAILED", f"{os.path.basename(p)}: {ex}")
                    QMessageBox.critical(self, "SUMA",
                                         f"Could not lock '{os.path.basename(p)}':\n\n{ex}\n\n"
                                         "The original file was NOT touched.")
            self.dash.refresh()

    def unlock_item(self, vid):
        item = next((m for m in self.engine.manifest if m["id"] == vid), None)
        if not item:
            return
        if not confirm_box(self, "> Unlock item?",
                           f"'{item['name']}' will be decrypted back to its original location."):
            return
        if os.path.lexists(item["orig"]):
            if not confirm_box(self, "> Overwrite?",
                               f"'{item['orig']}' already exists.\nOverwrite it with the vault copy?"):
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
