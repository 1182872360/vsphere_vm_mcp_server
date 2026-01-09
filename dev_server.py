#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
开发调试入口 - 用于 mcp dev 命令

使用方法:
    uv run mcp dev dev_server.py:mcp
"""

import os
import sys

# 将 src 目录添加到 Python 路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

# 使用绝对导入
from vsphere_mcp.server import mcp, run_server

# 硬编码环境变量（仅供开发调试）
os.environ["VSPHERE_HOST"] = "192.168.1.165"
os.environ["VSPHERE_USERNAME"] = "wushenxin"
os.environ["VSPHERE_PASSWORD"] = "wuShenxin!"
os.environ["VSPHERE_PORT"] = "443"

if __name__ == "__main__":
    run_server()
