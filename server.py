# -*- coding: utf-8 -*-
"""خادم التحديثات الوسيط (Render) — ODEJ Eloued

المبدأ:
- مفتاح GitHub يبقى هنا فقط (متغير بيئة) ولا يغادر الخادم أبداً.
- العميل يرسل مفتاح ترخيصه؛ الخادم يقارن بصمته (SHA256) بالقائمة المسموحة.
- الخادم لا يمرّر الملف الكبير: يعطي العميل رابط تنزيل مؤقتاً من GitHub (صالح دقائق)،
  فيحمّل العميل مباشرة من GitHub.
- الخادم لا يوقّع شيئاً: التوقيع (Ed25519) يُنجز على جهازك ويُرفع مع الإصدار،
  والعميل يتحقق منه بالمفتاح العام. فاختراق هذا الخادم لا يسمح بتمرير تحديث مزوّر.

متغيرات البيئة في Render:
    GITHUB_TOKEN    مفتاح fine-grained: قراءة Contents/Releases لهذا المستودع فقط
    REPO_OWNER, REPO_NAME
    LICENSE_HASHES  بصمات SHA256 للتراخيص، مفصولة بفواصل (أنشئها بـ make_license.py)

الإصدار في GitHub يجب أن يحوي أصلين: manifest.json والحزمة التي يسمّيها (حقل file).
"""
import hashlib
import hmac
import os
import re
import threading
import time

import requests
from flask import Flask, jsonify, request

from versioning import is_newer, parse_version

app = Flask(__name__)

GITHUB_API = "https://api.github.com"
HTTP_TIMEOUT = 20
CACHE_SECONDS = 60
RATE_LIMIT = 30          # طلبات
RATE_WINDOW = 600        # خلال 10 دقائق، لكل عنوان

_lock = threading.Lock()
_cache = {"at": 0.0, "value": None}
_hits = {}


# ───────────────────────── إعدادات ─────────────────────────
def _cfg():
    return (os.environ.get("GITHUB_TOKEN"), os.environ.get("REPO_OWNER"),
            os.environ.get("REPO_NAME"))


def _license_hashes():
    raw = os.environ.get("LICENSE_HASHES", "")
    return {h.strip().lower() for h in raw.split(",") if h.strip()}


def license_ok(key):
    """مقارنة بزمن ثابت؛ المفتاح نفسه لا يُخزَّن ولا يُسجَّل."""
    if not isinstance(key, str) or not (8 <= len(key) <= 200):
        return False
    digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
    ok = False
    for h in _license_hashes():
        ok |= hmac.compare_digest(digest, h)
    return ok


# ───────────────────────── أدوات ─────────────────────────
def _client_ip():
    xff = request.headers.get("X-Forwarded-For", "")
    return xff.split(",")[-1].strip() if xff else (request.remote_addr or "?")


def _rate_limited(ip):
    now = time.time()
    with _lock:
        q = [t for t in _hits.get(ip, []) if now - t < RATE_WINDOW]
        q.append(now)
        _hits[ip] = q
        if len(_hits) > 5000:               # تنظيف
            for k in [k for k, v in _hits.items() if not v or now - v[-1] > RATE_WINDOW]:
                _hits.pop(k, None)
        return len(q) > RATE_LIMIT


def _gh_headers(accept="application/vnd.github+json"):
    token, _, _ = _cfg()
    return {"Authorization": f"Bearer {token}", "Accept": accept,
            "X-GitHub-Api-Version": "2022-11-28"}


def _latest_release():
    """آخر إصدار + محتوى manifest.json (مخزّن مؤقتاً دقيقة)."""
    token, owner, repo = _cfg()
    now = time.time()
    with _lock:
        if _cache["value"] and now - _cache["at"] < CACHE_SECONDS:
            return _cache["value"]
    r = requests.get(f"{GITHUB_API}/repos/{owner}/{repo}/releases/latest",
                     headers=_gh_headers(), timeout=HTTP_TIMEOUT)
    if r.status_code != 200:
        raise RuntimeError(f"github release status {r.status_code}")
    assets = {a["name"]: a for a in r.json().get("assets", [])}
    if "manifest.json" not in assets:
        raise RuntimeError("manifest.json missing in release")
    m = requests.get(assets["manifest.json"]["url"],
                     headers=_gh_headers("application/octet-stream"), timeout=HTTP_TIMEOUT)
    if m.status_code != 200:
        raise RuntimeError(f"manifest status {m.status_code}")
    value = {"manifest": m.json(), "assets": assets}
    with _lock:
        _cache.update(at=now, value=value)
    return value


def _temp_download_url(asset):
    """رابط مؤقت موقَّع من GitHub (لا يحتاج مفتاحاً، ويُمنع تتبّع التحويل حتى لا نمرّر المفتاح)."""
    r = requests.get(asset["url"], headers=_gh_headers("application/octet-stream"),
                     timeout=HTTP_TIMEOUT, allow_redirects=False)
    loc = r.headers.get("Location")
    if r.status_code not in (301, 302, 303, 307, 308) or not loc:
        raise RuntimeError(f"no redirect from github ({r.status_code})")
    return loc


# ───────────────────────── المسارات ─────────────────────────
@app.get("/health")
def health():
    return jsonify({"ok": True})


@app.post("/check-update")
def check_update():
    token, owner, repo = _cfg()
    if not (token and owner and repo) or not _license_hashes():
        return jsonify({"error": "server_not_configured"}), 500
    if _rate_limited(_client_ip()):
        return jsonify({"error": "too_many_requests"}), 429

    body = request.get_json(silent=True) or {}
    if not license_ok(body.get("license")):
        return jsonify({"error": "invalid_license"}), 403

    try:
        rel = _latest_release()
        manifest = rel["manifest"]
        try:
            parse_version(manifest.get("version"))
        except ValueError:
            app.logger.error("bad version in manifest: %r", manifest.get("version"))
            return jsonify({"error": "bad_manifest"}), 502
        if not is_newer(manifest.get("version"), body.get("version")):
            return jsonify({"update": False, "version": manifest.get("version")})
        asset = rel["assets"].get(manifest.get("file"))
        if not asset:
            return jsonify({"error": "package_missing"}), 502
        return jsonify({"update": True, "manifest": manifest,
                        "download_url": _temp_download_url(asset)})
    except Exception as e:          # لا نكشف التفاصيل للعميل
        app.logger.error("update check failed: %s", e)
        return jsonify({"error": "upstream_error"}), 502


if __name__ == "__main__":      # للتجربة المحلية فقط؛ في Render: gunicorn server:app
    app.run(host="127.0.0.1", port=5000)
