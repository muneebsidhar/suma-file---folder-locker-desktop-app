import os
from PySide6.QtGui import QImage, qRed, qGreen, qBlue, qRgb


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


STEGO_MAGIC = b"SUMA1"
