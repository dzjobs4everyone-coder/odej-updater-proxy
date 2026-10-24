# -*- coding: utf-8 -*-
"""واجهة التحديث للبرنامج. نفس الواجهة البرمجية القديمة تماماً:
    UpdateChecker(APP_VERSION): الإشارتان finished(bool, str, str) و progress(int)
    apply_update_and_restart(zip_path) -> (ok, err)
فلا يتغير شيء في main_window ولا settings_dialogs. يعمل مع PyQt6 أو PySide6.
"""
import os
import subprocess
import sys
import shutil
import tempfile

try:
    from PyQt6.QtCore import QThread, pyqtSignal
except ImportError:                                   # PySide6
    from PySide6.QtCore import QThread, Signal as pyqtSignal

from update_core import UpdateClient

PROXY_URL = "https://odej-updater-proxy.onrender.com"
# المفتاح العام (Base64) الناتج عن make_keys.py. فارغ = التحديث معطّل بأمان حتى تضعه.
UPDATE_PUBLIC_KEY = ""


# ───────── مفتاح الترخيص ─────────
def _data_dir():
    try:
        import data_paths
        return str(data_paths.data_dir())
    except Exception:
        return os.getcwd()


def _license_file():
    return os.path.join(_data_dir(), "license.key")


def load_license():
    key = os.environ.get("ODEJ_LICENSE", "").strip()
    if key:
        return key
    try:
        with open(_license_file(), encoding="utf-8") as f:
            return f.read().strip()
    except OSError:
        return ""


def save_license(key):
    with open(_license_file(), "w", encoding="utf-8") as f:
        f.write(key.strip())


# ───────── الفحص والتنزيل (في خيط مستقل) ─────────
class UpdateChecker(QThread):
    finished = pyqtSignal(bool, str, str)
    progress = pyqtSignal(int)

    def __init__(self, current_version):
        super().__init__()
        self.current_version = current_version

    def run(self):
        client = UpdateClient(self.current_version, PROXY_URL, UPDATE_PUBLIC_KEY, load_license(),
                              os.path.join(_data_dir(), "updates"))
        ok, msg, path = client.run(progress=self.progress.emit)
        self.finished.emit(ok, msg, path)


# ───────── التطبيق وإعادة التشغيل ─────────
def apply_update_and_restart(zip_path):
    """يشغّل أداة التطبيق (نسخة منها في مجلد مؤقت حتى لا تُستبدل أثناء عملها) ثم على الواجهة إغلاق البرنامج."""
    try:
        if not os.path.isfile(zip_path):
            return False, "ملف التحديث غير موجود."
        frozen = getattr(sys, "frozen", False)
        app_dir = os.path.dirname(sys.executable) if frozen else os.path.dirname(os.path.abspath(__file__))
        restart = sys.executable if frozen else ""
        if frozen:
            src = os.path.join(app_dir, "odej_updater.exe")
            if not os.path.isfile(src):
                return False, "أداة التحديث odej_updater.exe غير موجودة بجانب البرنامج."
            tmp = tempfile.mkdtemp(prefix="odej_upd_")
            helper = os.path.join(tmp, "odej_updater.exe")
            shutil.copy2(src, helper)
            cmd = [helper]
        else:                                          # وضع التطوير
            cmd = [sys.executable, os.path.join(app_dir, "apply_update.py")]
        cmd += ["--zip", zip_path, "--app-dir", app_dir, "--pid", str(os.getpid()),
                "--log", os.path.join(_data_dir(), "update.log")]
        if restart:
            cmd += ["--restart", restart]
        flags = 0x00000008 | 0x00000200 if os.name == "nt" else 0   # DETACHED_PROCESS | NEW_PROCESS_GROUP
        subprocess.Popen(cmd, close_fds=True, creationflags=flags)
        return True, ""
    except Exception as e:
        return False, f"تعذر تطبيق التحديث: {e}"
