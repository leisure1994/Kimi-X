"""
Web 工具集

提供网页搜索和 URL 内容获取功能，使用 httpx 进行异步 HTTP 请求。
"""

from __future__ import annotations

import asyncio
import logging
import re
from typing import Any
from urllib.parse import urljoin, urlparse

import httpx

from .base import AbstractTool, ApprovalLevel, ToolContext, ToolResult

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 默认请求头
# ---------------------------------------------------------------------------

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.0 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.0"
    ),
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;"
        "q=0.9,image/webp,*/*;q=0.8"
    ),
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Accept-Encoding": "gzip, deflate, br",
}

# ---------------------------------------------------------------------------
# HTML 清理辅助函数
# ---------------------------------------------------------------------------


def _strip_html(html: str) -> str:
    """从 HTML 中提取纯文本内容"""
    # 移除 script 和 style
    html = re.sub(r"<script[^>]*>.*?</script>", "", html, flags=re.DOTALL | re.IGNORECASE)
    html = re.sub(r"<style[^>]*>.*?</style>", "", html, flags=re.DOTALL | re.IGNORECASE)

    # 移除注释
    html = re.sub(r"<!--.*?-->", "", html, flags=re.DOTALL)

    # 转换常见块级标签为换行
    html = re.sub(r"</(p|div|h[1-6]|li|tr|pre|blockquote)>", "\n", html, flags=re.IGNORECASE)
    html = re.sub(r"<(br|hr)[^>]*>", "\n", html, flags=re.IGNORECASE)

    # 移除其余标签
    html = re.sub(r"<[^>]+>", "", html)

    # 解码 HTML 实体（简单版）
    import html as html_module
    html = html_module.unescape(html)

    # 清理空白
    lines = [line.strip() for line in html.split("\n")]
    lines = [line for line in lines if line]

    return "\n".join(lines)


def _extract_title(html: str) -> str:
    """从 HTML 中提取标题"""
    match = re.search(r"<title[^>]*>(.*?)</title>", html, re.IGNORECASE | re.DOTALL)
    if match:
        title = match.group(1).strip()
        import html as html_module
        return html_module.unescape(title)
    return ""


def _extract_links(html: str, base_url: str) -> list[dict[str, str]]:
    """从 HTML 中提取链接"""
    links = []
    seen = set()
    for match in re.finditer(r'<a[^>]+href=["\']([^"\']+)["\'][^>]*>(.*?)</a>', html, re.DOTALL | re.IGNORECASE):
        href = match.group(1).strip()
        text = re.sub(r'<[^>]+>', '', match.group(2)).strip()
        # 解析完整 URL
        full_url = urljoin(base_url, href)
        # 去重
        if full_url not in seen and text:
            seen.add(full_url)
            links.append({"url": full_url, "text": text})
    return links[:20]  # 最多20个链接


# ---------------------------------------------------------------------------
# 1. WebSearchTool
# ---------------------------------------------------------------------------


class WebSearchTool(AbstractTool):
    """网页搜索工具

    支持通过 DuckDuckGo 或模拟搜索结果进行网页搜索。
    如果未配置搜索 API，则返回模拟结果提示。
    """

    name = "web_search"
    description = (
        "搜索互联网上的信息。使用 DuckDuckGo 搜索引擎，"
        "返回相关的网页标题、摘要和链接。"
    )
    approval_required = ApprovalLevel.NONE
    parameters = {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "搜索关键词",
            },
            "max_results": {
                "type": "integer",
                "description": "最大返回结果数（1-20），默认 8",
                "default": 8,
            },
        },
        "required": ["query"],
    }

    async def execute(
        self,
        params: dict[str, Any],
        context: ToolContext,
    ) -> ToolResult:
        query = params["query"]
        max_results = min(max(params.get("max_results", 8), 1), 20)

        if not query or not query.strip():
            return ToolResult.fail("搜索关键词不能为空")

        # 尝试使用 DuckDuckGo 搜索
        try:
            results = await self._search_duckduckgo(query, max_results)
            if results:
                return ToolResult.ok(
                    self._format_results(results, query),
                    query=query,
                    result_count=len(results),
                    source="duckduckgo",
                )
        except Exception as exc:
            logger.warning("DuckDuckGo 搜索失败: %s", exc)

        # 备用：返回模拟结果
        return ToolResult.ok(
            self._simulate_results(query),
            query=query,
            result_count=0,
            source="simulated",
            note="当前使用模拟搜索结果。如需真实搜索，请安装 duckduckgo-search: pip install duckduckgo-search",
        )

    async def _search_duckduckgo(
        self, query: str, max_results: int
    ) -> list[dict[str, str]]:
        """使用 DuckDuckGo 进行搜索"""
        try:
            from duckduckgo_search import DDGS  # type: ignore[import-untyped]
        except ImportError:
            return []

        # DDGS 是同步的，在线程池中执行
        loop = asyncio.get_event_loop()

        def _do_search():
            with DDGS() as ddgs:
                return list(ddgs.text(query, max_results=max_results))

        results = await loop.run_in_executor(None, _do_search)
        return results

    def _format_results(self, results: list[dict[str, str]], query: str) -> str:
        """格式化搜索结果"""
        lines = [f"# 搜索结果: {query}", "=" * 60, ""]
        for i, r in enumerate(results, 1):
            title = r.get("title", "无标题")
            href = r.get("href", "")
            body = r.get("body", "")
            lines.append(f"## {i}. {title}")
            lines.append(f"链接: {href}")
            lines.append(f"摘要: {body[:300]}")
            lines.append("")
        return "\n".join(lines)

    def _simulate_results(self, query: str) -> str:
        """生成模拟搜索结果"""
        lines = [
            f"# 搜索: {query}",
            "=" * 60,
            "",
            "[模拟搜索结果 - 未配置真实搜索引擎]",
            "",
            "如需启用真实搜索，请安装:",
            "  pip install duckduckgo-search",
            "",
            f"搜索关键词 '{query}' 可能相关的主题:",
            "  1. 请使用 FetchUrlTool 直接获取已知 URL 的内容",
            "  2. 或在安装 duckduckgo-search 后重试",
            "",
        ]
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# 2. FetchUrlTool
# ---------------------------------------------------------------------------


class FetchUrlTool(AbstractTool):
    """获取 URL 内容

    异步 HTTP 请求工具，支持获取网页内容并自动提取文本。
    支持自定义请求头和超时设置。
    """

    name = "web_fetch"
    description = (
        "获取指定 URL 的内容。自动提取网页正文文本，"
        "支持自定义超时。返回网页标题、正文内容和关键链接。"
    )
    approval_required = ApprovalLevel.NONE
    parameters = {
        "type": "object",
        "properties": {
            "url": {
                "type": "string",
                "description": "要获取的 URL",
            },
            "timeout": {
                "type": "integer",
                "description": "请求超时（秒），默认 30",
                "default": 30,
            },
            "max_length": {
                "type": "integer",
                "description": "返回内容的最大字符数，默认 10000",
                "default": 10000,
            },
        },
        "required": ["url"],
    }

    async def execute(
        self,
        params: dict[str, Any],
        context: ToolContext,
    ) -> ToolResult:
        url = params["url"]
        timeout = params.get("timeout", 30)
        max_length = params.get("max_length", 10000)

        if not url or not url.strip():
            return ToolResult.fail("URL 不能为空")

        url = url.strip()

        # URL 格式验证
        parsed = urlparse(url)
        if not parsed.scheme or not parsed.netloc:
            return ToolResult.fail(f"无效的 URL 格式: {url}")

        # 仅允许 http/https
        if parsed.scheme not in ("http", "https"):
            return ToolResult.fail(f"不支持的协议: {parsed.scheme}，仅支持 http/https")

        try:
            async with httpx.AsyncClient(
                headers=DEFAULT_HEADERS,
                follow_redirects=True,
                timeout=httpx.Timeout(timeout),
            ) as client:
                response = await client.get(url)
                response.raise_for_status()

                content_type = response.headers.get("content-type", "").lower()
                html_content = response.text

                # 提取信息
                title = _extract_title(html_content)
                text_content = _strip_html(html_content)
                links = _extract_links(html_content, url)

                # 截断内容
                truncated = False
                if len(text_content) > max_length:
                    text_content = text_content[:max_length] + "\n\n... [内容已截断]"
                    truncated = True

                # 构建结果
                lines = [
                    f"# {title or '无标题'}",
                    f"URL: {url}",
                    f"状态: {response.status_code}",
                    f"类型: {content_type}",
                    f"大小: {len(html_content):,} 字符",
                    "=" * 60,
                    "",
                    text_content,
                ]

                # 添加关键链接
                if links:
                    lines.extend(["", "# 页面链接:", ""])
                    for link in links[:10]:
                        lines.append(f"- {link['text']}: {link['url']}")

                return ToolResult.ok(
                    "\n".join(lines),
                    url=url,
                    status_code=response.status_code,
                    title=title,
                    content_type=content_type,
                    truncated=truncated,
                    links_count=len(links),
                )

        except httpx.HTTPStatusError as exc:
            return ToolResult.fail(
                f"HTTP 错误: {exc.response.status_code} {exc.response.reason_phrase}\n"
                f"URL: {url}"
            )
        except httpx.RequestError as exc:
            return ToolResult.fail(f"请求失败: {exc}\nURL: {url}")
        except asyncio.TimeoutError:
            return ToolResult.fail(f"请求超时（{timeout} 秒）: {url}")
        except Exception as exc:
            return ToolResult.fail(f"获取 URL 失败: {exc}")
