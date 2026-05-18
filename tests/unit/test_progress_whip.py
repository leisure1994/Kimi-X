"""
Progress Whip 单元测试 — 纯本地，不耗 API token
"""

from __future__ import annotations

import pytest
import tempfile
import shutil
from pathlib import Path

from kimix.core.progress_whip import TaskProgress, ProgressWhip

pytestmark = pytest.mark.unit


class TestProgressWhip:
    """进度鞭子测试"""

    def test_task_progress_create(self) -> None:
        """任务进度创建"""
        task = TaskProgress(task_id="test_001", description="测试任务")
        assert task.task_id == "test_001"
        assert task.description == "测试任务"
        assert task.status == "running"

    def test_progress_whip_init(self) -> None:
        """进度鞭子初始化"""
        with tempfile.TemporaryDirectory() as tmpdir:
            whip = ProgressWhip(Path(tmpdir))
            assert whip is not None
