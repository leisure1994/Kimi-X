from __future__ import annotations

from .clawtip import ClawTipPayment
from .rtk import RTKCompressor
from .web_search_enhanced import WebSearch

# 注册到全局
import kimix.tools as _tools_mod

# 在已有注册表基础上增加新工具
def _register_new_tools():
    """注册新增的工具到全局注册表"""
    try:
        # ClawTip 支付
        _tools_mod.registry.register(ClawTipPayment())
    except Exception:
        pass
    
    try:
        # RTK Token压缩
        _tools_mod.registry.register(RTKCompressor())
    except Exception:
        pass
    
    try:
        # 增强搜索
        _tools_mod.registry.register(WebSearch())
    except Exception:
        pass

# 自动注册（延迟执行，确保基础工具先加载）
import atexit
atexit.register(_register_new_tools)

__all__ += [
    "ClawTipPayment",
    "RTKCompressor", 
    "WebSearch",
]
