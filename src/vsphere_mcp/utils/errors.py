# -*- coding: utf-8 -*-
"""
vSphere MCP Server - 错误处理模块

包含工具建议常量和 vSphere 错误解析函数
"""

import logging
from typing import Optional

from ..models import ErrorType, MCPError, ToolSuggestion


logger = logging.getLogger(__name__)


# =============================================================================
# 工具建议常量 - 用于错误响应中引导 LLM
# =============================================================================
TOOL_DESCRIBE_TEMPLATES = ToolSuggestion(
    tool_name="describeTemplates",
    description="查询可用的虚拟机模板列表",
    example_params={"cluster_name": "Cluster01"}
)

TOOL_DESCRIBE_HOSTS = ToolSuggestion(
    tool_name="describeHosts",
    description="查询可用的主机列表",
    example_params={"cluster_name": "Cluster01"}
)

TOOL_DESCRIBE_CLUSTERS = ToolSuggestion(
    tool_name="describeClusters",
    description="查询可用的集群列表",
    example_params={}
)

TOOL_DESCRIBE_FOLDERS = ToolSuggestion(
    tool_name="describeFolders",
    description="查询可用的文件夹列表",
    example_params={}
)

TOOL_DESCRIBE_RESOURCE_POOLS = ToolSuggestion(
    tool_name="describeResourcePools",
    description="查询可用的资源池列表",
    example_params={"cluster_name": "Cluster01"}
)


def parse_vsphere_error(error: Exception, operation: str) -> MCPError:
    """
    解析 vSphere API 错误，转换为结构化的 MCPError

    这是 MCP 最佳实践的核心：将底层 API 错误转换为对 LLM 友好的错误信息
    """
    error_msg = str(error)
    error_type = getattr(error, 'type', '') or ''

    # 连接错误
    if 'connection' in error_msg.lower() or 'timeout' in error_msg.lower():
        return MCPError(
            error_type=ErrorType.CONNECTION_ERROR,
            message=f"无法连接到 vSphere: {error_msg}",
            suggestion="请检查 vSphere 主机地址、端口和网络连接",
            related_tools=[]
        )

    # 权限不足
    if 'permission' in error_msg.lower() or 'access' in error_msg.lower() or 'unauthorized' in error_msg.lower():
        return MCPError(
            error_type=ErrorType.PERMISSION_DENIED,
            message=f"权限不足: {error_msg}",
            suggestion="请检查用户名、密码和权限配置"
        )

    # 资源不存在
    if 'not found' in error_msg.lower() or 'not exist' in error_msg.lower():
        if 'template' in operation.lower():
            return MCPError(
                error_type=ErrorType.RESOURCE_NOT_FOUND,
                parameter="template_name",
                message="指定的模板不存在",
                suggestion="请使用 describeTemplates 查询可用模板",
                related_tools=[TOOL_DESCRIBE_TEMPLATES]
            )
        elif 'host' in operation.lower():
            return MCPError(
                error_type=ErrorType.RESOURCE_NOT_FOUND,
                parameter="host_name",
                message="指定的主机不存在",
                suggestion="请使用 describeHosts 查询可用主机",
                related_tools=[TOOL_DESCRIBE_HOSTS]
            )
        elif 'cluster' in operation.lower():
            return MCPError(
                error_type=ErrorType.RESOURCE_NOT_FOUND,
                parameter="cluster_name",
                message="指定的集群不存在",
                suggestion="请使用 describeClusters 查询可用集群",
                related_tools=[TOOL_DESCRIBE_CLUSTERS]
            )

    # 资源不足
    if 'insufficient' in error_msg.lower() or 'quota' in error_msg.lower() or 'capacity' in error_msg.lower():
        return MCPError(
            error_type=ErrorType.QUOTA_EXCEEDED,
            message="资源不足",
            suggestion="请检查主机资源使用情况，或选择其他主机/集群"
        )

    # 冲突错误（名称重复）
    if 'duplicate' in error_msg.lower() or 'conflict' in error_msg.lower() or 'already exists' in error_msg.lower():
        return MCPError(
            error_type=ErrorType.INVALID_PARAMETER,
            parameter="vm_name",
            message="虚拟机名称已存在",
            suggestion="请使用不同的虚拟机名称"
        )

    # 默认错误处理
    return MCPError(
        error_type=ErrorType.API_ERROR,
        message=f"vSphere 操作失败: {error_msg}",
        suggestion="请检查参数是否正确，或稍后重试"
    )
