"""
vSphere VM MCP Server - 基于最佳实践的 vSphere 虚拟机创建 MCP 服务器

参考阿里云 ECS MCP 服务器架构模式实现，提供完整的错误处理、参数验证和工具注册机制。
"""

__version__ = "0.1.0"
__description__ = "vSphere VM MCP Server - 基于最佳实践的 vSphere 虚拟机创建 MCP 服务器"

from .main import (
    run_server,
    main,
    create_mcp_server,
    # 导出主要的类和函数供外部使用
    VSphereClient,
    ToolRegistry,
    MCPResult,
    MCPError,
    ErrorType,
)

__all__ = [
    "run_server",
    "main",
    "create_mcp_server",
    "VSphereClient",
    "ToolRegistry",
    "MCPResult",
    "MCPError",
    "ErrorType",
]