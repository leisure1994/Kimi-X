"""
文档格式转换工具 (Pandoc/Marker 风格)

支持多种文档格式互转：
- Markdown ↔ HTML
- Markdown ↔ PDF（通过 weasyprint 或 markdown-pdf）
- PDF → Markdown / 文本提取
- 代码高亮与格式化

集成到 Agent 的内容处理能力，让 Agent 能处理任意格式文档。
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import Any


class DocumentConverter:
    """文档格式转换器

    模拟 Pandoc + Marker 的核心功能，纯 Python 实现常用转换。
    复杂转换调用外部工具（pandoc、marker）。

    使用方式:
        converter = DocumentConverter()
        html = converter.md_to_html("# Hello\n\nWorld")
        md = converter.pdf_to_text("/path/to/file.pdf")
    """

    def __init__(self, pandoc_path: str = "pandoc", marker_path: str = "marker") -> None:
        self.pandoc_path = pandoc_path
        self.marker_path = marker_path
        self._has_pandoc = self._check_tool(pandoc_path)
        self._has_marker = self._check_tool(marker_path)

    # ── Markdown ↔ HTML ──

    def md_to_html(self, markdown: str, title: str = "") -> str:
        """Markdown 转 HTML"""
        if self._has_pandoc:
            return self._call_pandoc(markdown, "markdown", "html")
        else:
            return self._simple_md_to_html(markdown, title)

    def html_to_md(self, html: str) -> str:
        """HTML 转 Markdown"""
        if self._has_pandoc:
            return self._call_pandoc(html, "html", "markdown")
        else:
            return self._simple_html_to_md(html)

    # ── Markdown ↔ 文本 ──

    def md_to_text(self, markdown: str) -> str:
        """Markdown 转纯文本（去除标记）"""
        text = markdown
        # 去除标题标记
        text = re.sub(r'^#{1,6}\s+', '', text, flags=re.MULTILINE)
        # 去除加粗斜体
        text = re.sub(r'\*\*?|\_\_?', '', text)
        # 去除代码块
        text = re.sub(r'```[\s\S]*?```', '[code block]', text)
        # 去除行内代码
        text = re.sub(r'`([^`]+)`', r'\1', text)
        # 去除链接，保留文本
        text = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', text)
        # 去除图片
        text = re.sub(r'!\[([^\]]*)\]\([^)]+\)', r'[image: \1]', text)
        # 去除水平线
        text = re.sub(r'^-{3,}\s*$', '', text, flags=re.MULTILINE)
        return text.strip()

    # ── PDF 处理 ──

    def pdf_to_text(self, pdf_path: str, max_pages: int | None = None) -> str:
        """PDF 提取文本"""
        path = Path(pdf_path)
        if not path.exists():
            return f"[Error: File not found: {pdf_path}]"

        # 优先使用 marker（高精度）
        if self._has_marker:
            return self._call_marker(pdf_path, max_pages)

        # fallback 到纯文本提取（简单实现）
        return self._simple_pdf_extract(str(path))

    def pdf_to_md(self, pdf_path: str) -> str:
        """PDF 转 Markdown"""
        text = self.pdf_to_text(pdf_path)
        # 简单结构化：按段落分割，检测标题
        paragraphs = text.split('\n\n')
        md_lines = []
        for p in paragraphs:
            p = p.strip()
            if not p:
                continue
            # 检测可能的标题（短行、大写、无标点结尾）
            if len(p) < 100 and p.isupper() and not p.endswith(('.', '?', '!')):
                md_lines.append(f"## {p.title()}")
            else:
                md_lines.append(p)
        return '\n\n'.join(md_lines)

    # ── 代码格式化 ──

    def format_code(self, code: str, language: str = "python") -> str:
        """格式化代码（简单实现）"""
        lines = code.split('\n')
        formatted = []
        indent_level = 0
        for line in lines:
            stripped = line.strip()
            if not stripped:
                formatted.append('')
                continue
            # 减少缩进（遇到结束标记）
            if stripped.startswith(('}', ']', ')', 'end', 'else:', 'elif ', 'except', 'finally:')):
                indent_level = max(0, indent_level - 1)
            # 添加缩进
            formatted.append('    ' * indent_level + stripped)
            # 增加缩进（遇到开始标记）
            if stripped.endswith(('{', '[', '(', ':')) or stripped.startswith(('def ', 'class ', 'if ', 'for ', 'while ', 'try:', 'with ')):
                indent_level += 1
        return '\n'.join(formatted)

    # ── 内部工具 ──

    def _check_tool(self, tool: str) -> bool:
        """检查外部工具是否可用"""
        try:
            subprocess.run([tool, "--version"], capture_output=True, check=True, timeout=5)
            return True
        except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
            return False

    def _call_pandoc(self, input_text: str, from_fmt: str, to_fmt: str) -> str:
        """调用 pandoc 转换"""
        try:
            result = subprocess.run(
                [self.pandoc_path, "-f", from_fmt, "-t", to_fmt, "--wrap=none"],
                input=input_text,
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode == 0:
                return result.stdout
            else:
                return f"[Pandoc Error: {result.stderr}]"
        except Exception as e:
            return f"[Pandoc Error: {e}]"

    def _call_marker(self, pdf_path: str, max_pages: int | None = None) -> str:
        """调用 marker 提取 PDF"""
        try:
            cmd = [self.marker_path, "single", pdf_path]
            if max_pages:
                cmd.extend(["--max_pages", str(max_pages)])
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=60,
            )
            if result.returncode == 0:
                return result.stdout
            else:
                return f"[Marker Error: {result.stderr}]"
        except Exception as e:
            return f"[Marker Error: {e}]"

    def _simple_md_to_html(self, markdown: str, title: str = "") -> str:
        """简单 Markdown 转 HTML（无外部依赖）"""
        html = markdown
        # 标题
        html = re.sub(r'^#{6}\s+(.+)$', r'<h6>\1</h6>', html, flags=re.MULTILINE)
        html = re.sub(r'^#{5}\s+(.+)$', r'<h5>\1</h5>', html, flags=re.MULTILINE)
        html = re.sub(r'^#{4}\s+(.+)$', r'<h4>\1</h4>', html, flags=re.MULTILINE)
        html = re.sub(r'^#{3}\s+(.+)$', r'<h3>\1</h3>', html, flags=re.MULTILINE)
        html = re.sub(r'^#{2}\s+(.+)$', r'<h2>\1</h2>', html, flags=re.MULTILINE)
        html = re.sub(r'^#{1}\s+(.+)$', r'<h1>\1</h1>', html, flags=re.MULTILINE)
        # 加粗
        html = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', html)
        html = re.sub(r'__(.+?)__', r'<strong>\1</strong>', html)
        # 斜体
        html = re.sub(r'\*(.+?)\*', r'<em>\1</em>', html)
        html = re.sub(r'_(.+?)_', r'<em>\1</em>', html)
        # 代码块
        html = re.sub(r'```(\w+)?\n([\s\S]*?)```', r'<pre><code>\2</code></pre>', html)
        # 行内代码
        html = re.sub(r'`([^`]+)`', r'<code>\1</code>', html)
        # 链接
        html = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', r'<a href="\2">\1</a>', html)
        # 图片
        html = re.sub(r'!\[([^\]]*)\]\(([^)]+)\)', r'<img src="\2" alt="\1">', html)
        # 段落（简单处理）
        paragraphs = html.split('\n\n')
        wrapped = []
        for p in paragraphs:
            p = p.strip()
            if p and not p.startswith('<'):
                p = f'<p>{p}</p>'
            wrapped.append(p)
        html = '\n\n'.join(wrapped)
        # 包装 HTML 文档
        title_tag = f'<title>{title}</title>' if title else ''
        return f'<!DOCTYPE html>\n<html>\n<head>{title_tag}</head>\n<body>\n{html}\n</body>\n</html>'

    def _simple_html_to_md(self, html: str) -> str:
        """简单 HTML 转 Markdown"""
        md = html
        # 去除标签
        md = re.sub(r'</?(html|body|head|title|div|span)[^>]*>', '', md, flags=re.IGNORECASE)
        # 标题
        md = re.sub(r'<h1[^>]*>(.*?)</h1>', r'# \1', md, flags=re.IGNORECASE | re.DOTALL)
        md = re.sub(r'<h2[^>]*>(.*?)</h2>', r'## \1', md, flags=re.IGNORECASE | re.DOTALL)
        md = re.sub(r'<h3[^>]*>(.*?)</h3>', r'### \1', md, flags=re.IGNORECASE | re.DOTALL)
        # 加粗
        md = re.sub(r'<strong>(.*?)</strong>', r'**\1**', md, flags=re.IGNORECASE | re.DOTALL)
        md = re.sub(r'<b>(.*?)</b>', r'**\1**', md, flags=re.IGNORECASE | re.DOTALL)
        # 斜体
        md = re.sub(r'<em>(.*?)</em>', r'*\1*', md, flags=re.IGNORECASE | re.DOTALL)
        md = re.sub(r'<i>(.*?)</i>', r'*\1*', md, flags=re.IGNORECASE | re.DOTALL)
        # 代码
        md = re.sub(r'<code>(.*?)</code>', r'`\1`', md, flags=re.IGNORECASE | re.DOTALL)
        md = re.sub(r'<pre>(.*?)</pre>', r'```\n\1\n```', md, flags=re.IGNORECASE | re.DOTALL)
        # 链接
        md = re.sub(r'<a[^>]*href="([^"]*)"[^>]*>(.*?)</a>', r'[\2](\1)', md, flags=re.IGNORECASE | re.DOTALL)
        # 图片
        md = re.sub(r'<img[^>]*src="([^"]*)"[^>]*alt="([^"]*)"[^>]*/?>', r'![\2](\1)', md, flags=re.IGNORECASE)
        # 段落
        md = re.sub(r'<p[^>]*>(.*?)</p>', r'\1\n\n', md, flags=re.IGNORECASE | re.DOTALL)
        # 去除剩余标签
        md = re.sub(r'<[^>]+>', '', md)
        # 清理
        md = re.sub(r'\n{3,}', '\n\n', md)
        return md.strip()

    def _simple_pdf_extract(self, pdf_path: str) -> str:
        """简单 PDF 文本提取（使用 pdfplumber 或 PyPDF2）"""
        try:
            import pdfplumber
            with pdfplumber.open(pdf_path) as pdf:
                text_parts = []
                for i, page in enumerate(pdf.pages):
                    text = page.extract_text()
                    if text:
                        text_parts.append(text)
                return '\n\n'.join(text_parts)
        except ImportError:
            try:
                import PyPDF2
                with open(pdf_path, 'rb') as f:
                    reader = PyPDF2.PdfReader(f)
                    text_parts = []
                    for page in reader.pages:
                        text = page.extract_text()
                        if text:
                            text_parts.append(text)
                    return '\n\n'.join(text_parts)
            except ImportError:
                return "[Error: PDF extraction requires pdfplumber or PyPDF2. Install: pip install pdfplumber]"

    def get_stats(self) -> dict[str, Any]:
        """转换器状态"""
        return {
            "pandoc_available": self._has_pandoc,
            "marker_available": self._has_marker,
            "capabilities": [
                "md_to_html",
                "html_to_md",
                "md_to_text",
                "pdf_to_text",
                "pdf_to_md",
                "format_code",
            ],
        }
