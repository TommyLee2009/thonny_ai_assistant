"""
thonny-ai-assistant - 主模块
"""

import sys
import logging
import os

# 添加自身到插件路徑中確保可以被找到
plugin_dir = os.path.dirname(os.path.abspath(__file__))
if plugin_dir not in sys.path:
    sys.path.insert(0, plugin_dir)

try:
    # 使用与 pyproject.toml 中声明的插件入口一致的模块
    from thonnycontrib.thonny_ai_assistant import load_plugin as ai_load_plugin
except ImportError:
    try:
        # 兼容以包形式加载本目录的情况
        from .thonnycontrib.thonny_ai_assistant import (
            load_plugin as ai_load_plugin,
        )
    except ImportError as e:
        print(f"无法导入 thonny_ai_assistant_tool 模块: {e}")
        ai_load_plugin = None

def load():
    """插件入口点 - 由 Thonny 调用"""
    if ai_load_plugin:
        try:
            ai_load_plugin()
        except Exception as e:
            print(f"加载 thonny-ai-assistant 插件时出错: {e}")
            import traceback
            traceback.print_exc()
