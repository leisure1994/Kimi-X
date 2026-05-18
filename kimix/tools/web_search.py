"""
Web 搜索工具

Agent 可通过搜索引擎获取外部信息：
- 查找 API 文档
- 搜索库/框架的最新用法
- 查找错误解决方案
- 获取技术博客/教程

依赖: 需要搜索引擎 API key（如 SerpAPI、Tavily、或 kimi_search）
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any


@dataclass
class SearchResult:
    """搜索结果"""
    title: str
    url: str
    snippet: str
    source: str = "unknown"


class WebSearchTool:
    """Web 搜索工具

    支持多种搜索后端（按优先级尝试）：
    1. kimi_search（已集成，优先）
    2. tavily（如配置 API key）
    3. duckduckgo（免费，无需 key）

    用法:
        search = WebSearchTool()
        results = search.search("FastAPI latest version changelog")
        for r in results:
            print(f"{r.title}: {r.url}")
    """

    def __init__(self, api_key: str | None = None) -> None:
        self.api_key = api_key or os.environ.get("TAVILY_API_KEY")

    def search(
        self,
        query: str,
        limit: int = 5,
        include_content: bool = False,
    ) -> list[SearchResult]:
        """执行搜索

        Args:
            query: 搜索关键词
            limit: 返回结果数量
            include_content: 是否获取页面内容

        Returns:
            SearchResult 列表
        """
        # 优先尝试已集成的 kimi_search
        try:
            return self._search_kimi(query, limit, include_content)
        except Exception:
            pass

        # 尝试 Tavily
        if self.api_key:
            try:
                return self._search_tavily(query, limit)
            except Exception:
                pass

        # 降级到 DuckDuckGo
        try:
            return self._search_duckduckgo(query, limit)
        except Exception:
            pass

        # 全部失败，返回空
        return []

    def _search_kimi(
        self,
        query: str,
        limit: int,
        include_content: bool,
    ) -> list[SearchResult]:
        """使用 kimi_search（需 OpenClaw 环境）"""
        try:
            # 通过 OpenClaw 工具搜索
            results = self._call_kimi_search(query, limit, include_content)
            return [
                SearchResult(
                    title=r.get("title", "无标题"),
                    url=r.get("url", ""),
                    snippet=r.get("summary", "") or r.get("snippet", ""),
                    source="kimi_search",
                )
                for r in results
            ]
        except Exception as e:
            raise RuntimeError(f"kimi_search failed: {e}")

    def _call_kimi_search(
        self,
        query: str,
        limit: int,
        include_content: bool,
    ) -> list[dict[str, Any]]:
        """调用 kimi_search（内部实现）"""
        # 实际实现需要通过 OpenClaw 工具调用
        # 这里模拟，实际环境通过外部工具注入
        raise NotImplementedError("kimi_search requires OpenClaw runtime")

    def _search_tavily(self, query: str, limit: int) -> list[SearchResult]:
        """使用 Tavily API"""
        import urllib.request
        import json

        data = json.dumps({
            "api_key": self.api_key,
            "query": query,
            "search_depth": "basic",
            "max_results": limit,
        }).encode()

        req = urllib.request.Request(
            "https://api.tavily.com/search",
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read())

        return [
            SearchResult(
                title=r.get("title", "无标题"),
                url=r.get("url", ""),
                snippet=r.get("content", ""),
                source="tavily",
            )
            for r in result.get("results", [])
        ]

    def _search_duckduckgo(self, query: str, limit: int) -> list[SearchResult]:
        """使用 DuckDuckGo（免费，无需 API key）"""
        import urllib.request
        import urllib.parse
        import json

        url = "https://html.duckduckgo.com/html/"
        data = urllib.parse.urlencode({"q": query}).encode()

        req = urllib.request.Request(
            url,
            data=data,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            },
            method="POST",
        )

        with urllib.request.urlopen(req, timeout=30) as resp:
            html = resp.read().decode("utf-8", errors="ignore")

        # 简单解析 HTML 提取结果
        import re
        results = []
        for match in re.finditer(
            r'<a class="result__a" href="([^"]+)">([^<]+)</a>.*?<a class="result__snippet">([^<]+)</a>',
            html,
            re.DOTALL,
        ):
            if len(results) >= limit:
                break
            url, title, snippet = match.groups()
            results.append(SearchResult(
                title=title.strip(),
                url=url.strip(),
                snippet=snippet.strip(),
                source="duckduckgo",
            ))

        return results

    def fetch_page(self, url: str, max_chars: int = 5000) -> str:
        """获取页面内容

        Args:
            url: 页面 URL
            max_chars: 最大字符数

        Returns:
            页面文本内容
        """
        import urllib.request

        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            },
        )

        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                html = resp.read().decode("utf-8", errors="ignore")

            # 简单 HTML 到文本转换
            import re
            text = re.sub(r"<script[^>]*>.*?</script>", "", html, flags=re.DOTALL)
            text = re.sub(r"<style[^>]*>.*?</style>", "", text, flags=re.DOTALL)
            text = re.sub(r"<[^>]+>", " ", text)
            text = re.sub(r"\s+", " ", text).strip()
            return text[:max_chars]
        except Exception as e:
            return f"[ERROR] 无法获取页面: {e}"

    def to_tool_schema(self) -> dict[str, Any]:
        """返回工具注册表用的 schema"""
        return {
            "name": "web_search",
            "description": "通过搜索引擎查找外部信息：API 文档、错误解决方案、技术博客等",
            "parameters": {
                "query": "搜索关键词（用英文效果更好）",
                "limit": "返回结果数量（默认 5）",
            },
        }
