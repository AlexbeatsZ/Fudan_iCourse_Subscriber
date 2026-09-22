"""Authenticated, paginated Canvas reads and an explicit messaging API."""
from __future__ import annotations

from urllib.parse import parse_qs, unquote, urljoin, urlparse
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

BASE = "https://elearning.fudan.edu.cn"


class CanvasError(RuntimeError):
    """Safe error text: never includes signed URLs, cookies or credentials."""


class Client:
    def __init__(self, session=None):
        self.session = session or requests.Session()
        self.session.trust_env = False
        self.session.headers.update({"User-Agent": "Mozilla/5.0", "Accept": "application/json"})
        retry = Retry(total=3, backoff_factor=1, status_forcelist=[429, 500, 502, 503, 504],
                      allowed_methods=["GET", "HEAD"], respect_retry_after_header=True)
        self.session.mount("https://", HTTPAdapter(max_retries=retry))

    def close(self):
        self.session.close()

    def login(self):
        # Reuse only the university IDP primitives, not iCourse/WebVPN sessions.
        from desktop.downloader import credentials
        from src.api.webvpn import WebVPNSession
        account, password = credentials()
        auth = WebVPNSession()
        auth.session.close()
        auth.session = self.session
        landing = self.session.get(BASE + "/login/cas", timeout=(15, 60))
        parsed = urlparse(landing.url)
        query = parse_qs(parsed.query or parsed.fragment.partition("?")[2])
        lck = query.get("lck", [""])[0]
        entity = query.get("entityId", [BASE])[0]
        if not lck or entity != BASE:
            raise CanvasError("未取得 eLearning 统一认证上下文")
        chain, request_type = auth._query_auth_methods(lck, entity)
        encrypted = auth._encrypt_password(password, auth._get_public_key())
        token = auth._auth_execute(account, encrypted, lck, entity, chain, request_type)
        ticket = auth._get_cas_ticket(token)
        if urlparse(ticket).hostname != urlparse(BASE).hostname:
            raise CanvasError("统一认证返回了非 eLearning 票据")
        response = self.session.get(ticket, timeout=(15, 90))
        if response.status_code != 200:
            raise CanvasError("eLearning 会话建立失败")
        self.get("/api/v1/users/self/profile")
        return self

    def _url(self, path):
        url = urljoin(BASE + "/", path)
        parsed = urlparse(url)
        if parsed.scheme != "https" or parsed.netloc != urlparse(BASE).netloc:
            raise CanvasError("拒绝跨站 API 地址")
        return url

    def request(self, method, path, **kwargs):
        headers = dict(kwargs.pop("headers", {}))
        if method != "GET":
            csrf = next((c.value for c in self.session.cookies if c.name == "_csrf_token"), "")
            headers["X-CSRF-Token"] = unquote(csrf)
        response = self.session.request(method, self._url(path), headers=headers,
                                        timeout=(15, 60), **kwargs)
        if response.status_code >= 400:
            raise CanvasError(f"eLearning API HTTP {response.status_code}")
        if "json" not in response.headers.get("Content-Type", ""):
            raise CanvasError("登录已失效或 API 未返回 JSON")
        return response

    def get(self, path, **kwargs):
        return self.request("GET", path, **kwargs).json()

    def pages(self, path, params=None):
        url, seen = self._url(path), set()
        params = {"per_page": 100, **(params or {})}
        while url:
            if url in seen:
                raise CanvasError("API 分页形成循环")
            seen.add(url)
            response = self.request("GET", url, params=params)
            rows = response.json()
            if not isinstance(rows, list):
                raise CanvasError("API 列表结构不符合预期")
            yield from rows
            url = response.links.get("next", {}).get("url")
            params = None

    def courses(self, all_terms=False):
        params = {"include[]": "term"}
        if not all_terms:
            params["enrollment_state"] = "active"
        return list(self.pages("/api/v1/courses", params))

    def folders(self, course_id):
        return list(self.pages(f"/api/v1/courses/{int(course_id)}/folders"))

    def files(self, course_id):
        return list(self.pages(f"/api/v1/courses/{int(course_id)}/files"))

    def announcements(self, course_id):
        return list(self.pages(f"/api/v1/courses/{int(course_id)}/discussion_topics", {"only_announcements": "true"}))

    def conversations(self):
        # Listing conversations does not mark messages read.
        return list(self.pages("/api/v1/conversations", {"scope": "inbox"}))

    def send_message(self, recipients, subject, body, *, confirmed=False):
        """Explicit API for future callers; never invoked by polling/CLI."""
        if not confirmed or not recipients or not body.strip():
            raise ValueError("发送需要明确确认、收件人和正文")
        return self.request("POST", "/api/v1/conversations", json={
            "recipients": [str(x) for x in recipients], "subject": subject, "body": body,
        }).json()

    def download(self, file, target):
        """Fresh Canvas metadata contains a scoped signed file URL."""
        url = file.get("url") or f"{BASE}/files/{int(file['id'])}/download"
        self._url(url)  # Only the school may initiate the download redirect.
        import os
        import re
        import time
        expected = int(file["size"])
        for attempt in range(6):
            start = target.stat().st_size if target.exists() else 0
            if start == expected and target.exists():
                return
            if start > expected:
                start = 0
            headers = {"Accept-Encoding": "identity"}
            if start:
                headers["Range"] = f"bytes={start}-"
            try:
                with self.session.get(url, headers=headers, stream=True, timeout=(15, 45)) as response:
                    if response.status_code not in (200, 206):
                        raise CanvasError(f"文件下载 HTTP {response.status_code}")
                    if response.status_code == 206:
                        match = re.fullmatch(r"bytes (\d+)-(\d+)/(\d+)", response.headers.get("Content-Range", ""))
                        if not match or int(match[1]) != start or int(match[3]) != expected:
                            raise CanvasError("文件续传范围与预期不一致")
                    else:
                        start = 0  # Server ignored Range; restart safely.
                    actual_type = response.headers.get("Content-Type", "").split(";")[0]
                    if actual_type == "text/html" and file.get("content-type") != "text/html":
                        raise CanvasError("文件下载返回了登录页面")
                    with target.open("ab" if start else "wb") as out:
                        for chunk in response.iter_content(64 * 1024):
                            out.write(chunk)
                        out.flush()
                        os.fsync(out.fileno())
                    if target.stat().st_size != expected:
                        raise requests.exceptions.ChunkedEncodingError("incomplete body")
                    return
            except requests.RequestException:
                if attempt == 5:
                    raise CanvasError("文件传输中断，已保留断点，下次自动续传") from None
                print(f"文件 {file['id']} 传输中断，重试 {attempt + 1}/5", flush=True)
                time.sleep(min(attempt + 1, 5))
