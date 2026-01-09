# -*- coding: utf-8 -*-
"""
vSphere MCP Server - 工具函数包导出
"""

from .errors import (
    TOOL_DESCRIBE_TEMPLATES,
    TOOL_DESCRIBE_HOSTS,
    TOOL_DESCRIBE_CLUSTERS,
    TOOL_DESCRIBE_FOLDERS,
    TOOL_DESCRIBE_RESOURCE_POOLS,
    parse_vsphere_error,
)

from .validators import (
    validate_vm_name,
    validate_template_name,
    validate_cluster_name,
    validate_cpu_memory,
)

__all__ = [
    # 错误处理
    "TOOL_DESCRIBE_TEMPLATES",
    "TOOL_DESCRIBE_HOSTS",
    "TOOL_DESCRIBE_CLUSTERS",
    "TOOL_DESCRIBE_FOLDERS",
    "TOOL_DESCRIBE_RESOURCE_POOLS",
    "parse_vsphere_error",
    # 验证函数
    "validate_vm_name",
    "validate_template_name",
    "validate_cluster_name",
    "validate_cpu_memory",
]
