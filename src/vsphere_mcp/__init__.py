# -*- coding: utf-8 -*-
"""
vSphere MCP Server

一个基于 MCP 最佳实践的 vSphere 虚拟机管理服务器。
"""

from .server import mcp, run_server
from .client import VSphereClient, get_vsphere_client
from .models import MCPResult, MCPError, ErrorType

__version__ = "0.1.0"

__all__ = [
    "mcp",
    "run_server",
    "VSphereClient",
    "get_vsphere_client",
    "MCPResult",
    "MCPError",
    "ErrorType",
]
