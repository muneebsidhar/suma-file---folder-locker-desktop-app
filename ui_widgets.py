import os
import sys
import json
import math
import shutil
import tempfile
import zipfile
from datetime import datetime
from config import find_config, load_avatar_pm, profile_path, save_profile_pic
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


NEON = "#00ff88"


BRIGHT = "#d1ffe6"


DIM = "#58b88a"


DARKB = "#14532d"


RED = "#ff4d4d"


ORANGE = "#ffb020"


ICON_PATHS = ["D:/SUMA/assets/samu_icon.png", "D:/SUMA/assets/suma_icon.png"]


RESIZE_M = 7


def mono(bold=False, size=10):
    f = QFont("Consolas", size)
    f.setBold(bold)
    return f


def find_icon():
    from config import BASE_DIR
    extra = [os.path.join(BASE_DIR, "assets", "samu_icon.png"),
             os.path.join(BASE_DIR, "assets", "suma_icon.png")]
    for p in ICON_PATHS + extra:
        if os.path.isfile(p):
            pm = QPixmap(p)
            if not pm.isNull():
                return pm
    return QPixmap()


def find_company_logo(nocap=False):
    from config import BASE_DIR
    if nocap:
        names = ["D:/SUMA/assets/mrs-krypton-logo-nocap-dark.png",
                 os.path.join(BASE_DIR, "assets", "mrs-krypton-logo-nocap-dark.png")]
    else:
        names = ["D:/SUMA/assets/mrs-krypton-logo-dark.png",
                 "D:/SUMA/assets/mrs-krypton-logo.png",
                 os.path.join(BASE_DIR, "assets", "mrs-krypton-logo-dark.png"),
                 os.path.join(BASE_DIR, "assets", "mrs-krypton-logo.png")]
    for p in names:
        if os.path.isfile(p):
            pm = QPixmap(p)
            if not pm.isNull():
                return pm
    return QPixmap()


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
        for key, label in [("vault", "> Vault"), ("log", "> Activity Log"), ("settings", "> Settings")]:
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
        fh = QHBoxLayout()
        fh.setSpacing(8)
        fh.setAlignment(Qt.AlignCenter)
        logolab = QLabel()
        clogo = find_company_logo()
        if not clogo.isNull():
            logolab.setPixmap(clogo.scaled(40, 40, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        fh.addWidget(logolab)
        cname = QLabel("MRS KRYPTON")
        cname.setFont(mono(True, 11))
        cname.setStyleSheet(f"color:{BRIGHT}; background:transparent; border:none;")
        fh.addWidget(cname)
        lay.addLayout(fh)
        csub = QLabel("SUMA - File & Folder Locker")
        csub.setFont(mono(False, 8))
        csub.setStyleSheet(f"color:{DIM}; background:transparent; border:none;")
        csub.setAlignment(Qt.AlignCenter)
        lay.addWidget(csub)
        cline = QFrame()
        cline.setFixedHeight(1)
        cline.setStyleSheet(f"background:{DARKB}; border:none;")
        lay.addWidget(cline)
        c1 = QLabel("© 2026 MRS KRYPTON")
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
