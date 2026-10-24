# -*- coding: utf-8 -*-
import hashlib, os, unittest
from unittest import mock

KEY = "TEST-LICENSE-KEY-123456"
os.environ.update(GITHUB_TOKEN="ghp_fake", REPO_OWNER="o", REPO_NAME="r",
                  LICENSE_HASHES=hashlib.sha256(KEY.encode()).hexdigest())
import server


class Resp:
    def __init__(self, status=200, js=None, headers=None):
        self.status_code, self._js, self.headers = status, js, headers or {}
    def json(self):
        return self._js


MANIFEST = {"version": "V01C-1008", "file": "update-1.0.8.zip", "sha256": "a" * 64,
            "size": 10, "data_format": 1, "signature": "x"}
RELEASE = {"assets": [{"name": "manifest.json", "url": "https://api/m"},
                      {"name": "update-1.0.8.zip", "url": "https://api/z"}]}
calls = []


def fake_get(url, headers=None, timeout=None, allow_redirects=True):
    calls.append((url, allow_redirects, dict(headers or {})))
    if url.endswith("/releases/latest"):
        return Resp(200, RELEASE)
    if url == "https://api/m":
        return Resp(200, MANIFEST)
    if url == "https://api/z":
        return Resp(302, headers={"Location": "https://objects.example/signed?x=1"})
    return Resp(404)


class T(unittest.TestCase):
    def setUp(self):
        server._cache.update(at=0.0, value=None)
        server._hits.clear()
        calls.clear()
        self.c = server.app.test_client()

    def post(self, **b):
        with mock.patch.object(server.requests, "get", fake_get):
            return self.c.post("/check-update", json=b)

    def test_bad_license(self):
        self.assertEqual(self.post(license="wrong-key-123", version="V01C-1001").status_code, 403)
        self.assertEqual(self.post(version="V01C-1001").status_code, 403)

    def test_update_available(self):
        r = self.post(license=KEY, version="V01C-1007")
        j = r.get_json()
        self.assertTrue(j["update"])
        self.assertEqual(j["download_url"], "https://objects.example/signed?x=1")
        self.assertEqual(j["manifest"]["version"], "V01C-1008")

    def test_no_update_when_current(self):
        self.assertFalse(self.post(license=KEY, version="V01C-1008").get_json()["update"])
        self.assertFalse(self.post(license=KEY, version="V01D-1001").get_json()["update"])

    def test_token_never_sent_to_redirect_and_no_follow(self):
        self.post(license=KEY, version="V01C-1001")
        z = [c for c in calls if c[0] == "https://api/z"][0]
        self.assertFalse(z[1])                       # allow_redirects=False
        self.assertTrue(all(c[0].startswith("https://api") or "github" in c[0] for c in calls))

    def test_token_not_in_response(self):
        self.assertNotIn("ghp_fake", self.post(license=KEY, version="V01C-1001").get_data(as_text=True))

    def test_no_open_proxy_route(self):
        self.assertEqual(self.c.get("/download?url=https://evil.example").status_code, 404)

    def test_rate_limit(self):
        for _ in range(server.RATE_LIMIT):
            self.post(license="x" * 10, version="V01C-1001")
        self.assertEqual(self.post(license="x" * 10, version="V01C-1001").status_code, 429)

    def test_versions(self):
        self.assertGreater(server.parse_version("V01C-1010"), server.parse_version("V01C-1009"))


if __name__ == "__main__":
    unittest.main()
