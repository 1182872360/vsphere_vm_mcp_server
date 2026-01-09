# -*- coding: utf-8 -*-
"""
vSphere MCP Server - 数据模型基础模块

MCP 最佳实践：
- 结构化错误类型
- 统一响应模型
"""

from enum import Enum
from typing import Dict, Any, Optional, List

from pydantic import Field, BaseModel, ConfigDict


# =============================================================================
# 错误类型枚举
# =============================================================================
class ErrorType(str, Enum):
    """错误类型枚举，帮助 LLM 理解错误性质"""
    MISSING_PARAMETER = "MISSING_PARAMETER"          # 必需参数缺失
    INVALID_PARAMETER = "INVALID_PARAMETER"          # 参数格式或值无效
    RESOURCE_NOT_FOUND = "RESOURCE_NOT_FOUND"        # 资源不存在
    PERMISSION_DENIED = "PERMISSION_DENIED"          # 权限不足
    QUOTA_EXCEEDED = "QUOTA_EXCEEDED"                # 配额超限
    DEPENDENCY_MISSING = "DEPENDENCY_MISSING"        # 依赖资源缺失
    API_ERROR = "API_ERROR"                          # API 调用错误
    PRECONDITION_FAILED = "PRECONDITION_FAILED"      # 前置条件不满足
    CONNECTION_ERROR = "CONNECTION_ERROR"            # 连接错误


# =============================================================================
# 基础模型
# =============================================================================
class MyBaseModel(BaseModel):
    model_config = ConfigDict(json_dumps_params={'ensure_ascii': False})


class ToolSuggestion(MyBaseModel):
    """工具建议模型 - 引导 LLM 调用正确的工具"""
    tool_name: str = Field(description="建议调用的工具名称")
    description: str = Field(description="调用该工具的原因说明")
    example_params: Optional[Dict[str, Any]] = Field(default=None, description="示例参数")


class MCPError(MyBaseModel):
    """
    MCP 最佳实践：结构化错误响应

    这个模型确保错误信息对 LLM 友好，包含：
    1. 错误类型 - 便于 LLM 分类处理
    2. 人类可读消息 - 便于理解问题
    3. 解决方案建议 - 告诉 LLM 如何修复
    4. 相关工具 - 引导 LLM 调用正确的工具
    """
    error_type: ErrorType = Field(description="错误类型")
    message: str = Field(description="人类可读的错误描述")
    parameter: Optional[str] = Field(default=None, description="出错的参数名")
    suggestion: str = Field(description="给 LLM 的解决方案建议")
    related_tools: Optional[List[ToolSuggestion]] = Field(
        default=None,
        description="相关工具推荐，LLM 可以调用这些工具来解决问题"
    )

    def __str__(self) -> str:
        """格式化输出，便于 LLM 解析"""
        parts = [
            f"[{self.error_type.value}] {self.message}",
            f"建议: {self.suggestion}"
        ]
        if self.related_tools:
            tools_info = ", ".join([f"{t.tool_name}({t.description})" for t in self.related_tools])
            parts.append(f"相关工具: {tools_info}")
        return "\n".join(parts)


class MCPResult(MyBaseModel):
    """
    MCP 最佳实践：统一响应模型

    所有工具响应都使用这个模型，确保结构一致性
    """
    success: bool = Field(description="操作是否成功")
    data: Optional[Any] = Field(default=None, description="成功时的数据")
    error: Optional[MCPError] = Field(default=None, description="失败时的错误信息")
    request_id: Optional[str] = Field(default=None, description="请求 ID，用于追踪")
