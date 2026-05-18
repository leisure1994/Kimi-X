"""python -m kimix` 入口模块.

支持通过命令行直接运行 Kimi-Agent:
    $ python -m kimix
    $ python -m kimix "帮我分析项目结构"
    $ python -m kimix --version
"""

from __future__ import annotations

import sys


def main() -> int:
    """python -m kimix` 的主入口函数.

    当包通过 `python -m kimix` 运行时，此函数会被调用。
    它负责加载 CLI 入口点并将控制权转移给真正的 CLI 处理器。

    Returns:
        int: 程序退出码，0 表示成功，非 0 表示错误
    """
    try:
        # 延迟导入以避免循环依赖和加快模块加载速度
        from kimix.cli import main as cli_main

        cli_main()
        return 0
    except ImportError:
        print(
            "错误: CLI 模块尚未初始化。\n"
            "当前仅基础设施层可用，完整 CLI 功能将在后续版本中提供。\n\n"
            "可用命令:\n"
            "  python -m kimix.config    查看配置信息\n",
            file=sys.stderr,
        )
        return 1
    except KeyboardInterrupt:
        print("\n已取消", file=sys.stderr)
        return 130
    except Exception as exc:  # noqa: BLE001
        print(f"运行时错误: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
