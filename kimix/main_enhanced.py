"""
Kimi-Agent 主入口 — 集成所有增强能力（v8.1）

新增集成（v8.1）：
- 自动经济模式提示系统 (AutoEconomyPrompter)
  • 闲置3小时 → 提示开启闲时兼职模式
  • 复杂任务3倍基线 → 提示开启赏金模式
  • 未开通 ClawTip → 自动引导开通流程
  • 24小时防打扰冷却

v8 集成：
- 进度鞭 / 文言文省Token / 核心准则 / 赏金+兼职+云端 / 股票/定价/小红书/进化
v7 集成：
- 四层记忆L0-L3 / Hindsight / Superpowers / gstack / 搜索 / RTK / ClawTip / Cron
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from kimix.config.config_manager import ConfigManager
from kimix.core.agent import Agent
from kimix.core.auto_economy import AutoEconomyPrompter
from kimix.core.classical_chinese import ClassicalChineseCompressor
from kimix.core.context import AgentContext, ContextManager
from kimix.core.core_rules import inject_core_rules, CORE_RULES_SHORT
from kimix.core.error_classifier import classify_error
from kimix.core.preflight import PreflightCheck
from kimix.core.progress_whip import ProgressWhip
from kimix.core.agent_economy import (
    AgentCloudPlatform, BountyEngine, FreelanceEngine,
    create_bounty_mode, create_freelance_mode, create_cloud_platform,
)
from kimix.llm.kimi_client import KimiClient
from kimix.memory.enhanced_memory import EnhancedMemorySystem
from kimix.tools.clawtip import ClawTipPayment
from kimix.tools.document_converter import DocumentConverter
from kimix.tools.registry import ToolRegistry
from kimix.tools.rtk import RTKCompressor
from kimix.tools.web_search_enhanced import WebSearch


class EnhancedKimiAgent:
    """增强版 Kimi-Agent — v8.1 完整版（含自动经济提示）"""

    def __init__(self, config_path: str | None = None, agent_id: str | None = None) -> None:
        self.agent_id = agent_id or f"agent_{int(time.time())}"
        self.config = ConfigManager(config_path)
        self.llm = KimiClient(self.config)
        self.memory = EnhancedMemorySystem()
        self.tools = ToolRegistry()
        self.tools.create_default_registry()

        # ── v8.1 自动经济提示 ──
        self.auto_prompter: AutoEconomyPrompter | None = None

        # ── v8 核心 ──
        self.progress_whip = ProgressWhip()
        self.cc_compressor = ClassicalChineseCompressor(enabled=True)
        self.cloud_platform: AgentCloudPlatform | None = None
        self.bounty_engine: BountyEngine | None = None
        self.freelance_engine: FreelanceEngine | None = None

        # ── v7 增强工具 ──
        self._setup_enhanced_tools()

        # ── 核心组件 ──
        self.preflight = PreflightCheck(self.tools)
        self.context_manager = ContextManager()
        self.agent_context = AgentContext()

    def _setup_enhanced_tools(self) -> None:
        # ClawTip
        try:
            self.clawtip = ClawTipPayment()
            # 初始化经济系统
            self.cloud_platform = create_cloud_platform(self.clawtip)
            self.bounty_engine = create_bounty_mode(self.clawtip)
            self.freelance_engine = create_freelance_mode(self.agent_id, self.clawtip)
            # v8.1: 初始化自动提示器
            self.auto_prompter = AutoEconomyPrompter(self.clawtip)
        except Exception:
            self.clawtip = None
            self.cloud_platform = None
            self.bounty_engine = None
            self.freelance_engine = None
            self.auto_prompter = None

        # RTK
        self.rtk = RTKCompressor(enabled=True)

        # 搜索
        try:
            self.web_search = WebSearch()
        except Exception:
            self.web_search = None

        # 文档转换
        self.doc_converter = DocumentConverter()

    # ── 主执行循环 ──

    async def run(self, user_input: str) -> str:
        """执行用户请求，含复杂度检测和空闲重置"""
        # v8.1: 记录活动（重置空闲计时器）
        if self.auto_prompter:
            self.auto_prompter.idle_detector.record_activity("user_input")

        # v8.1: 检测任务复杂度，提示赏金模式
        bounty_prompt = None
        if self.auto_prompter:
            bounty_prompt = self.auto_prompter.check_complexity_and_prompt(user_input)

        # 1. 注册任务到进度鞭
        task_id = f"task_{int(time.time())}"
        self.progress_whip.register(task_id, f"处理: {user_input[:50]}", steps_total=5)

        try:
            # 2. 自检鞭策
            alerts = self.progress_whip.whip_check()
            for a in alerts:
                pass  # 内部鞭策，零 Token

            self.progress_whip.step(task_id, "记录对话")

            # 3. 记录对话
            self.memory.record_conversation("user", user_input)

            # 4. 获取上下文
            self.progress_whip.step(task_id, "召回记忆")
            context = self.memory.get_context_for(user_input)

            # 5. 构建增强提示
            enhanced_prompt = self._build_enhanced_prompt(user_input, context)

            self.progress_whip.step(task_id, "预检")

            # 6. 预检
            preflight_result = self.preflight.run(enhanced_prompt)
            if not preflight_result.success:
                self.progress_whip.fail(task_id, f"预检失败: {preflight_result.message}")
                return f"[预检未通过] {preflight_result.message}"

            self.progress_whip.step(task_id, "调用 LLM")

            # 7. 调用 LLM
            response = await self.llm.chat(enhanced_prompt)

            self.progress_whip.step(task_id, "归档")

            # 8. 记录响应 + 知识提取
            self.memory.record_conversation("assistant", response)
            self.memory.extract_knowledge("assistant", response)

            # 9. 完成
            self.progress_whip.complete(task_id, "响应已生成")

            # v8.1: 如果检测到了赏金提示，在响应前附加
            if bounty_prompt:
                return f"{bounty_prompt}\n\n---\n\n{response}"

            return response

        except Exception as e:
            self.progress_whip.fail(task_id, str(e))
            raise

    def check_idle_prompt(self) -> str | None:
        """
        检查是否应提示兼职模式（闲置3小时以上）。
        应在 Agent 心跳/后台轮询时调用。
        """
        if not self.auto_prompter:
            return None
        return self.auto_prompter.check_idle_and_prompt()

    def handle_economy_response(self, mode: str, user_response: str) -> str:
        """
        处理用户对经济模式提示的响应。

        Args:
            mode: "freelance" 或 "bounty"
            user_response: 用户回复文本
        """
        if not self.auto_prompter:
            return "自动提示系统未初始化。"
        return self.auto_prompter.handle_user_response(mode, user_response)

    def _build_enhanced_prompt(self, user_input: str, context: dict) -> str:
        """构建增强提示"""
        parts = ["# 系统提示\n\n你是 Kimi-Agent，一个增强型 AI 助手。\n"]

        # 注入核心准则
        parts.append(f"\n{CORE_RULES_SHORT}\n")

        # 注入用户画像
        persona = context.get("persona")
        if persona:
            parts.append(f"\n## 用户画像\n{json.dumps(persona, ensure_ascii=False)}\n")

        # 相关事实
        facts = context.get("facts", [])
        if facts:
            parts.append(f"\n## 相关事实\n" + "\n".join(f"- {f}" for f in facts[:10]) + "\n")

        # 场景
        scenarios = context.get("scenarios", [])
        if scenarios:
            parts.append(f"\n## 相关场景\n" + "\n".join(f"- {s}" for s in scenarios[:5]) + "\n")

        # 知识图谱
        entities = context.get("entities", [])
        if entities:
            parts.append(f"\n## 相关实体\n")
            for e in entities[:10]:
                parts.append(f"- {e.get('name', '')} ({e.get('type', '')})\n")

        parts.append(f"\n# 用户请求\n\n{user_input}\n")
        return "".join(parts)

    # ── 经济系统 API ──

    def start_bounty_mode(
        self, title: str, description: str, total_bounty: int,
        stages: list[dict], **kwargs,
    ) -> dict:
        if not self.bounty_engine:
            return {"error": "ClawTip 未配置，无法启动赏金模式"}
        task = self.bounty_engine.create_bounty(
            title=title, description=description,
            total_bounty=total_bounty,
            owner_agent=self.agent_id,
            stages_plan=stages,
            **kwargs,
        )
        return {
            "mode": "bounty",
            "task_id": task.task_id,
            "title": task.title,
            "total_bounty": task.bounty_total,
            "stages": len(task.stages),
        }

    def start_freelance_mode(
        self, capabilities: list[str], hourly_rate: int,
        token_budget: int, max_complexity: str = "medium",
    ) -> dict:
        if not self.freelance_engine:
            return {"error": "ClawTip 未配置，无法启动兼职模式"}
        self.freelance_engine.configure(
            capabilities=capabilities,
            hourly_rate=hourly_rate,
            token_budget=token_budget,
            max_complexity=max_complexity,
        )
        result = self.freelance_engine.register_to_cloud()
        return {"mode": "freelance", **result}

    def get_economy_stats(self) -> dict:
        stats = {
            "bounty_mode": self.bounty_engine.get_task_report(list(self.bounty_engine.tasks.keys())[-1])
                if self.bounty_engine and self.bounty_engine.tasks else None,
            "freelance_mode": self.freelance_engine.get_earnings_report()
                if self.freelance_engine else None,
            "cloud_platform": self.cloud_platform.get_platform_stats()
                if self.cloud_platform else None,
        }
        return stats

    def get_progress_report(self) -> str:
        return self.progress_whip.generate_report()

    def get_auto_prompt_stats(self) -> dict:
        """获取自动提示系统统计"""
        if not self.auto_prompter:
            return {"error": "自动提示系统未初始化"}
        return self.auto_prompter.get_stats()

    def get_setup_guide(self) -> str:
        guides = ["# Kimi-Agent v8.1 配置指南\n"]
        if self.clawtip:
            guides.append(self.clawtip.get_setup_guide())
        guides.append("\n## 核心准则\n")
        guides.append("Agent 核心准则已自动注入到每次对话中，不可关闭。")
        guides.append("\n## 经济系统\n")
        guides.append("赏金模式: agent.start_bounty_mode(...)")
        guides.append("兼职模式: agent.start_freelance_mode(...)")
        guides.append("\n## 自动提示\n")
        guides.append("闲置3小时 → 自动提示兼职模式")
        guides.append("复杂任务3倍基线 → 自动提示赏金模式")
        guides.append("未开通 ClawTip → 自动引导开通流程")
        return "\n".join(guides)

    def get_stats(self) -> dict:
        return {
            "memory": self.memory.get_stats(),
            "tools": len(self.tools.list_tools()) if hasattr(self.tools, 'list_tools') else 0,
            "clawtip": self.clawtip.get_stats() if self.clawtip else None,
            "rtk": self.rtk.get_stats(),
            "web_search": self.web_search.get_stats() if self.web_search else None,
            "doc_converter": self.doc_converter.get_stats(),
            "progress_whip": self.progress_whip.get_stats(),
            "cc_compressor": self.cc_compressor.get_stats(),
            "auto_prompter": self.get_auto_prompt_stats() if self.auto_prompter else None,
            "economy": self.get_economy_stats() if (self.bounty_engine or self.freelance_engine) else None,
        }


async def main():
    parser = argparse.ArgumentParser(description="Kimi-Agent v8.1 — 增强版")
    parser.add_argument("--config", help="配置文件路径")
    parser.add_argument("--setup", action="store_true", help="显示配置指南")
    parser.add_argument("--stats", action="store_true", help="显示统计")
    parser.add_argument("--test-tools", action="store_true", help="测试所有工具")
    parser.add_argument("--progress", action="store_true", help="进度鞭报告")
    parser.add_argument("--bounty-demo", action="store_true", help="赏金模式演示")
    parser.add_argument("--freelance-demo", action="store_true", help="兼职模式演示")
    parser.add_argument("--auto-prompt-stats", action="store_true", help="自动提示统计")
    parser.add_argument("--check-idle", action="store_true", help="检查空闲并提示")
    args = parser.parse_args()

    agent = EnhancedKimiAgent(args.config)

    if args.setup:
        print(agent.get_setup_guide())
        return
    if args.stats:
        print(json.dumps(agent.get_stats(), indent=2, ensure_ascii=False))
        return
    if args.progress:
        print(agent.get_progress_report())
        return
    if args.auto_prompt_stats:
        print(json.dumps(agent.get_auto_prompt_stats(), indent=2, ensure_ascii=False))
        return
    if args.check_idle:
        prompt = agent.check_idle_prompt()
        if prompt:
            print(prompt)
        else:
            print("未达到提示条件（需闲置3小时以上且不在冷却期）")
        return
    if args.bounty_demo:
        result = agent.start_bounty_mode(
            title="自动编写测试用例",
            description="为 Kimi-Agent 的核心模块编写 pytest 测试",
            total_bounty=5000,
            stages=[
                {"title": "设计测试框架", "description": "编写 conftest.py 和 fixtures", "bounty": 1000},
                {"title": "核心模块测试", "description": "测试 agent.py 主要功能", "bounty": 2000},
                {"title": "边缘情况测试", "description": "异常输入和边界测试", "bounty": 1500},
                {"title": "集成测试", "description": "端到端流程验证", "bounty": 500},
            ],
        )
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return
    if args.freelance_demo:
        result = agent.start_freelance_mode(
            capabilities=["python", "testing", "documentation"],
            hourly_rate=500,
            token_budget=100000,
        )
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return
    if args.test_tools:
        print("测试工具...")
        if agent.clawtip:
            order = agent.clawtip.create_order(amount=1, description="测试", question="测试")
            print(f"ClawTip: {order}")
        compressed = agent.rtk.compress("ls", "a.py\nb.py")
        print(f"RTK: {compressed}")
        if agent.web_search:
            results = agent.web_search.search("Python", source="ddg")
            print(f"Search: {len(results)} 条")
        print(f"\n进度鞭报告:\n{agent.get_progress_report()}")
        print(f"\n自动提示统计:\n{json.dumps(agent.get_auto_prompt_stats(), indent=2, ensure_ascii=False)}")
        return

    # 交互模式
    print("Kimi-Agent v8.1 已启动。输入 'exit' 退出。\n")
    print("提示: 我可以自动检测空闲和任务复杂度，推荐经济模式。\n")

    while True:
        try:
            user_input = input("\n👤 > ").strip()
            if user_input.lower() in ("exit", "quit", "bye"):
                print("再见！")
                break
            if not user_input:
                # v8.1: 空输入时检查空闲提示
                idle_prompt = agent.check_idle_prompt()
                if idle_prompt:
                    print(f"\n💡 {idle_prompt}")
                continue

            # v8.1: 处理经济模式响应（如果用户回复的是模式相关指令）
            economy_keywords = ["开启兼职", "开启赏金", "不用了", "自己来", "教我开通", "已开通", "现在开启", "停止兼职"]
            if any(kw in user_input for kw in economy_keywords):
                # 检测是响应哪个模式的提示
                mode = "freelance" if any(k in user_input for k in ["兼职", "freelance"]) else "bounty"
                response = agent.handle_economy_response(mode, user_input)
                print(f"\n🤖 > {response}")
                continue

            response = await agent.run(user_input)
            print(f"\n🤖 > {response}")

        except KeyboardInterrupt:
            print("\n再见！")
            break
        except Exception as e:
            print(f"\n❌ 错误: {e}")


if __name__ == "__main__":
    asyncio.run(main())
