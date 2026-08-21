"""抓取微信公众号文章正文。

微信公众号文章详情页（mp.weixin.qq.com/s/...）可匿名访问，正文在
`<div id="js_content">`、标题在 `<h1 id="activity-name">`、公众号名在
`<a id="js_name">`。用 httpx 直连 + 正则提取，零额外依赖。

失败（反爬验证页 / 网络异常）向上抛异常，由调用方降级为「请手动粘贴文本」。
"""

from __future__ import annotations

import html as _html
import re
from typing import Any

import httpx

_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/122.0 Safari/537.36"
)

_TITLE_RE = re.compile(r'<h1[^>]*id="activity-name"[^>]*>(.*?)</h1>', re.DOTALL)
_OG_TITLE_RE = re.compile(r'<meta[^>]*property="og:title"[^>]*content="([^"]*)"', re.DOTALL)
_SOURCE_RE = re.compile(r'<a[^>]*id="js_name"[^>]*>(.*?)</a>', re.DOTALL)
_CONTENT_START_RE = re.compile(r'<div[^>]*id="js_content"[^>]*>')


def _strip_tags(text: str) -> str:
    return re.sub(r"<[^>]+>", "", text)


def _extract_title(html_text: str) -> str:
    m = _TITLE_RE.search(html_text) or _OG_TITLE_RE.search(html_text)
    return _strip_tags(m.group(1)).strip() if m else ""


def _extract_source(html_text: str) -> str:
    m = _SOURCE_RE.search(html_text)
    return _strip_tags(m.group(1)).strip() if m else ""


def _extract_content(html_text: str) -> str:
    m = _CONTENT_START_RE.search(html_text)
    if not m:
        return ""
    # 从 js_content 起点取 60k 字符，足够覆盖整篇正文。
    body = html_text[m.start() : m.start() + 60_000]
    body = re.sub(r"<script.*?</script>", "", body, flags=re.DOTALL)
    body = re.sub(r"<style.*?</style>", "", body, flags=re.DOTALL)
    body = re.sub(r"</p>", "\n", body)
    body = re.sub(r"<br\s*/?>", "\n", body)
    body = _strip_tags(body)
    body = _html.unescape(body)
    body = re.sub(r"[ \t]+\n", "\n", body)
    body = re.sub(r"\n{3,}", "\n\n", body)
    return body.strip()


def fetch_article(url: str, timeout: float = 20.0) -> dict[str, Any]:
    """抓取一篇公众号文章，返回 {url, title, source, raw_text}。

    Raises:
        RuntimeError: 抓取失败或未提取到正文。
    """
    resp = httpx.get(
        url,
        headers={"User-Agent": _UA},
        timeout=timeout,
        follow_redirects=True,
    )
    if resp.status_code >= 400:
        raise RuntimeError(f"抓取失败 {resp.status_code}")
    html_text = resp.text

    raw_text = _extract_content(html_text)
    if not raw_text or len(raw_text) < 20:
        raise RuntimeError("未能提取正文（可能触发反爬验证页）")

    return {
        "url": url,
        "title": _extract_title(html_text),
        "source": _extract_source(html_text),
        "raw_text": raw_text,
    }
