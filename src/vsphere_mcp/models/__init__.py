# -*- coding: utf-8 -*-
"""
vSphere MCP Server - 模型包导出
"""

from .base import (
    ErrorType,
    MyBaseModel,
    ToolSuggestion,
    MCPError,
    MCPResult,
)

from .vsphere import (
    VMInfo,
    VMTemplateInfo,
    HostInfo,
    ClusterInfo,
    FolderInfo,
    ResourcePoolInfo,
)

__all__ = [
    # 基础模型
    "ErrorType",
    "MyBaseModel",
    "ToolSuggestion",
    "MCPError",
    "MCPResult",
    # vSphere 模型
    "VMInfo",
    "VMTemplateInfo",
    "HostInfo",
    "ClusterInfo",
    "FolderInfo",
    "ResourcePoolInfo",
]
