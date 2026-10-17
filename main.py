import sys
from PySide6.QtWidgets import QApplication, QSplashScreen, QMessageBox
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import (QPixmap, QPainter, QColor, QPen, QBrush,
                           QRadialGradient, QIcon)

from config import BASE_DIR
from ui_widgets import mono, find_icon, find_company_logo, NEON, BRIGHT, DIM, DARKB
from app import MainWindow


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
        lp = icon_pm.scaled(88, 88, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        p.drawPixmap((w - 88) // 2, 36, lp)
    p.setPen(QColor(BRIGHT))
    p.setFont(mono(True, 32))
    p.drawText(0, 138, w, 48, Qt.AlignCenter, "SUMA")
    p.setPen(QColor(DIM))
    p.setFont(mono(False, 11))
    p.drawText(0, 184, w, 28, Qt.AlignCenter, "YOUR FILES ARE SAFELY SECURED.")
    p.setPen(QColor(DIM))
    p.setFont(mono(False, 10))
    p.drawText(0, h - 148, w, 20, Qt.AlignCenter, "By:")
    clogo = find_company_logo(nocap=True)
    if clogo.isNull():
        clogo = find_company_logo()
    if not clogo.isNull():
        lp = clogo.scaled(100, 62, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        p.drawPixmap((w - lp.width()) // 2, h - 126, lp)
    p.setPen(QColor(BRIGHT))
    p.setFont(mono(True, 12))
    p.drawText(0, h - 60, w, 20, Qt.AlignCenter, "MRS KRYPTON")
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
        print("icon not found")
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
