# -*- coding: utf-8 -*-
"""
vSphere MCP Server - 参数验证模块
"""

import re
from typing import Optional

from ..models import ErrorType, MCPError
from .errors import TOOL_DESCRIBE_TEMPLATES, TOOL_DESCRIBE_CLUSTERS


def validate_vm_name(vm_name: Optional[str]) -> Optional[MCPError]:
    """验证虚拟机名称"""
    if not vm_name:
        return MCPError(
            error_type=ErrorType.MISSING_PARAMETER,
            parameter="vm_name",
            message="缺少必需参数: vm_name (虚拟机名称)",
            suggestion="请提供有效的虚拟机名称，如 'web-server-01'"
        )

    # 检查名称长度和格式
    if len(vm_name) < 3 or len(vm_name) > 80:
        return MCPError(
            error_type=ErrorType.INVALID_PARAMETER,
            parameter="vm_name",
            message=f"虚拟机名称长度必须在 3-80 字符之间: '{vm_name}'",
            suggestion="请使用 3-80 个字符的名称"
        )

    # 检查特殊字符
    if not re.match(r'^[a-zA-Z0-9_-]+$', vm_name):
        return MCPError(
            error_type=ErrorType.INVALID_PARAMETER,
            parameter="vm_name",
            message=f"虚拟机名称包含无效字符: '{vm_name}'",
            suggestion="请使用字母、数字、下划线和连字符"
        )

    return None


def validate_template_name(template_name: Optional[str]) -> Optional[MCPError]:
    """验证模板名称"""
    if not template_name:
        return MCPError(
            error_type=ErrorType.MISSING_PARAMETER,
            parameter="template_name",
            message="缺少必需参数: template_name (模板名称)",
            suggestion="请先使用 describeTemplates 查询可用模板",
            related_tools=[TOOL_DESCRIBE_TEMPLATES]
        )
    return None


def validate_cluster_name(cluster_name: Optional[str]) -> Optional[MCPError]:
    """验证集群名称"""
    if not cluster_name:
        return MCPError(
            error_type=ErrorType.MISSING_PARAMETER,
            parameter="cluster_name",
            message="缺少必需参数: cluster_name (集群名称)",
            suggestion="请先使用 describeClusters 查询可用集群",
            related_tools=[TOOL_DESCRIBE_CLUSTERS]
        )
    return None


def validate_cpu_memory(cpu: Optional[int], memory: Optional[int]) -> Optional[MCPError]:
    """验证 CPU 和内存参数"""
    if cpu and (cpu < 1 or cpu > 128):
        return MCPError(
            error_type=ErrorType.INVALID_PARAMETER,
            parameter="cpu",
            message=f"CPU 核数必须在 1-128 之间: {cpu}",
            suggestion="请调整 CPU 核数到有效范围"
        )

    if memory and (memory < 512 or memory > 1048576):
        return MCPError(
            error_type=ErrorType.INVALID_PARAMETER,
            parameter="memory",
            message=f"内存大小必须在 512MB-1TB 之间: {memory}MB",
            suggestion="请调整内存大小到有效范围"
        )

    return None
