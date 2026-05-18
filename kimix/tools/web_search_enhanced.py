"""
增强型网页搜索工具 (Tavily + DuckDuckGo)

提供多源搜索能力：
- Tavily: AI 专用搜索，高质量结果，1000 次/月免费
- DuckDuckGo: 零成本兜底搜索
- 结果聚合与去重
- 自动摘要生成

集成到 Agent 的感知层，让 Agent 能读懂互联网。
"""

from __future__ import annotations

import json
import os
import re
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from typing import Any


@dataclass
class SearchResult:
    """搜索结果"""
    title: str
    url: str
    snippet: str
    source: str  # tavily / ddg
    score: float = 0.0
    content: str = ""  # 全文（如果获取了）


class WebSearch:
    """增强型网页搜索

    支持 Tavily + DuckDuckGo 双源搜索，自动 fallback。

    使用方式:
        search = WebSearch()
        results = search.search("Python best practices 2024")
        for r in results:
            print(f"{r.title}: {r.url}")
    """

    def __init__(
        self,
        tavily_api_key: str | None = None,
        max_results: int = 10,
        include_answer: bool = True,
    ) -> None:
        self.tavily_api_key = tavily_api_key or os.environ.get("TAVILY_API_KEY", "")
        self.max_results = max_results
        self.include_answer = include_answer
        self.user_agent = "Mozilla/5.0 (compatible; Kimi-Agent/1.0)"

    # ── 主搜索接口 ──

    def search(self, query: str, source: str = "auto") -> list[SearchResult]:
        """执行搜索

        Args:
            query: 搜索查询
            source: "tavily" | "ddg" | "auto"（自动选择）

        Returns:
            搜索结果列表
        """
        if source == "auto":
            # 优先 Tavily，如果不可用则 fallback 到 DDG
            if self.tavily_api_key:
                try:
                    return self._search_tavily(query)
                except Exception:
                    pass
            return self._search_ddg(query)

        elif source == "tavily":
            return self._search_tavily(query)

        elif source == "ddg":
            return self._search_ddg(query)

        else:
            raise ValueError(f"Unknown source: {source}")

    def search_with_answer(self, query: str, source: str = "auto") -> dict[str, Any]:
        """搜索并生成答案

        Returns:
            {
                "query": query,
                "answer": "AI 生成的答案摘要",
                "results": [SearchResult, ...],
                "sources": ["url1", "url2"],
            }
        """
        results = self.search(query, source)

        # 生成简单答案（基于搜索结果拼接）
        answer_parts = []
        for i, r in enumerate(results[:5]):
            answer_parts.append(f"[{i+1}] {r.title}: {r.snippet}")

        return {
            "query": query,
            "answer": "\n".join(answer_parts) if answer_parts else "未找到相关结果",
            "results": results,
            "sources": [r.url for r in results],
            "total": len(results),
        }

    # ── Tavily 搜索 ──

    def _search_tavily(self, query: str) -> list[SearchResult]:
        """Tavily AI 搜索"""
        if not self.tavily_api_key:
            raise ValueError("Tavily API key not configured")

        url = "https://api.tavily.com/search"
        payload = {
            "api_key": self.tavily_api_key,
            "query": query,
            "max_results": self.max_results,
            "include_answer": self.include_answer,
            "search_depth": "basic",
        }

        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "User-Agent": self.user_agent,
            },
            method="POST",
        )

        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))

        results = []
        for item in data.get("results", []):
            results.append(SearchResult(
                title=item.get("title", ""),
                url=item.get("url", ""),
                snippet=item.get("content", item.get("snippet", "")),
                source="tavily",
                score=item.get("score", 0.0),
            ))

        return results

    # ── DuckDuckGo 搜索 ──

    def _search_ddg(self, query: str) -> list[SearchResult]:
        """DuckDuckGo 搜索（HTML 解析）"""
        encoded_query = urllib.parse.quote(query)
        url = f"https://html.duckduckgo.com/html/?q={encoded_query}"

        req = urllib.request.Request(
            url,
            headers={"User-Agent": self.user_agent},
        )

        with urllib.request.urlopen(req, timeout=30) as resp:
            html = resp.read().decode("utf-8")

        results = []
        # 解析搜索结果
        # DuckDuckGo HTML 格式：
        # <a class="result__a" href="...">title</a>
        # <a class="result__snippet">snippet</a>

        link_pattern = re.compile(
            r'<a[^>]*class="result__a"[^>]*href="([^"]*)"[^>]*>(.*?)</a>',
            re.DOTALL | re.IGNORECASE,
        )
        snippet_pattern = re.compile(
            r'<a[^>]*class="result__snippet"[^>]*>(.*?)</a>',
            re.DOTALL | re.IGNORECASE,
        )

        links = link_pattern.findall(html)
        snippets = snippet_pattern.findall(html)

        for i, (href, title) in enumerate(links[:self.max_results]):
            # 清理标题（去除 HTML 标签）
            title_clean = re.sub(r'<[^>]+>', '', title).strip()
            snippet = re.sub(r'<[^>]+>', '', snippets[i]).strip() if i < len(snippets) else ""

            # 处理 DDG 重定向链接
            if href.startswith("//"):
                href = "https:" + href
            elif href.startswith("/"):
                href = "https://duckduckgo.com" + href

            results.append(SearchResult(
                title=title_clean,
                url=href,
                snippet=snippet,
                source="ddg",
                score=max(1.0 - i * 0.1, 0.1),  # 排名越靠前分数越高
            ))

        return results

    # ── 内容获取 ──

    def fetch_content(self, url: str, max_chars: int = 5000) -> str:
        """获取网页全文内容（简化版）"""
        try:
            req = urllib.request.Request(
                url,
                headers={"User-Agent": self.user_agent},
            )
            with urllib.request.urlopen(req, timeout=15) as resp:
                html = resp.read().decode("utf-8", errors="ignore")

            # 简单清理 HTML
            text = re.sub(r'<script[^>]*>.*?</script>', '', html, flags=re.DOTALL | re.IGNORECASE)
            text = re.sub(r'<style[^>]*>.*?</style>', '', text, flags=re.DOTALL | re.IGNORECASE)
            text = re.sub(r'<[^>]+>', ' ', text)
            text = re.sub(r'\s+', ' ', text).strip()

            return text[:max_chars]
        except Exception as e:
            return f"[获取失败: {e}]"

    # ── 批量搜索 ──

    def batch_search(self, queries: list[str], source: str = "auto") -> dict[str, list[SearchResult]]:
        """批量搜索"""
        return {q: self.search(q, source) for q in queries}

    # ── 配置检查 ──

    def is_tavily_available(self) -> bool:
        """Tavily 是否可用"""
        return bool(self.tavily_api_key)

    def get_stats(self) -> dict[str, Any]:
        return {
            "tavily_available": self.is_tavily_available(),
            "max_results": self.max_results,
            "include_answer": self.include_answer,
        }
