import os

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
