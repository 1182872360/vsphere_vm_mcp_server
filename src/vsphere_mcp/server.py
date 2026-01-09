# -*- coding: utf-8 -*-
"""
vSphere MCP Server - 服务器入口模块

MCP 服务器的主入口，包含：
- ToolRegistry：工具注册类
- lifespan：生命周期管理
- mcp：FastMCP 实例
- run_server：服务器运行函数
"""

import os
import logging
from contextlib import asynccontextmanager
from collections.abc import AsyncGenerator

from mcp.server.fastmcp import FastMCP

from .client import PYVMOMI_AVAILABLE
from .tools import (
    describe_templates,
    describe_hosts,
    describe_clusters,
    describe_folders,
    describe_resource_pools,
    describe_vms,
    create_vm_from_template,
)


logger = logging.getLogger(__name__)


# =============================================================================
# 工具注册类
# =============================================================================
class ToolRegistry:
    """工具注册类 - 管理所有 MCP 工具的注册"""

    def __init__(self, mcp_instance):
        self.mcp = mcp_instance

    def register_tools(self):
        """注册所有 MCP 工具"""
        self._register_query_tools()
        self._register_lifecycle_tools()
        return self.mcp

    def _register_query_tools(self):
        """注册查询类工具"""
        self.mcp.tool(
            name="describeTemplates",
            description="查询可用的虚拟机模板列表。创建虚拟机前应先调用此工具",
            annotations={"title": "查询虚拟机模板", "readOnlyHint": True}
        )(describe_templates)

        self.mcp.tool(
            name="describeHosts",
            description="查询可用的 ESXi 主机列表及其资源使用情况",
            annotations={"title": "查询主机列表", "readOnlyHint": True}
        )(describe_hosts)

        self.mcp.tool(
            name="describeClusters",
            description="查询可用的集群列表",
            annotations={"title": "查询集群", "readOnlyHint": True}
        )(describe_clusters)

        self.mcp.tool(
            name="describeFolders",
            description="查询可用的文件夹列表",
            annotations={"title": "查询文件夹", "readOnlyHint": True}
        )(describe_folders)

        self.mcp.tool(
            name="describeResourcePools",
            description="查询可用的资源池列表",
            annotations={"title": "查询资源池", "readOnlyHint": True}
        )(describe_resource_pools)

        self.mcp.tool(
            name="describeVMs",
            description="查询虚拟机列表，支持按集群和名称筛选",
            annotations={"title": "查询虚拟机", "readOnlyHint": True}
        )(describe_vms)

    def _register_lifecycle_tools(self):
        """注册生命周期管理工具"""
        self.mcp.tool(
            name="createVMFromTemplate",
            description=(
                "从模板创建虚拟机。创建前需要准备: "
                "1) vm_name - 虚拟机名称; "
                "2) template_name - 可通过 describeTemplates 查询; "
                "3) cluster_name - 可通过 describeClusters 查询; "
                "4) 可选: cpu, memory_mb, folder_name, resource_pool_name"
            ),
            annotations={"title": "创建虚拟机", "readOnlyHint": False, "destructiveHint": False}
        )(create_vm_from_template)


# =============================================================================
# 生命周期管理
# =============================================================================
@asynccontextmanager
async def lifespan(app) -> AsyncGenerator[None, None]:
    """MCP 服务器生命周期管理"""
    logger.info("初始化 vSphere MCP Server...")

    # 初始化应用状态
    if not hasattr(app, 'state') or app.state is None:
        class AppState:
            pass
        app.state = AppState()

    # 从环境变量读取 vSphere 配置
    app.state.vsphere_host = os.getenv("VSPHERE_HOST")
    app.state.vsphere_username = os.getenv("VSPHERE_USERNAME")
    app.state.vsphere_password = os.getenv("VSPHERE_PASSWORD")
    app.state.vsphere_port = int(os.getenv("VSPHERE_PORT", "443"))

    logger.info(f"vSphere 配置: {app.state.vsphere_host}")

    # 注册工具
    registry = ToolRegistry(app)
    registry.register_tools()

    yield

    logger.info("关闭 vSphere MCP Server...")


# =============================================================================
# FastMCP 实例创建
# =============================================================================
mcp = FastMCP(
    "vSphereVMAssistant",
    lifespan=lifespan,
    instructions=(
        "vSphere 虚拟机管理助手，提供虚拟机创建、查询等功能。\n\n"
        "**工具使用指南**:\n"
        "1. 查询资源: 使用 describe* 工具获取可用的模板、主机、集群等\n"
        "2. 创建虚拟机: 使用 createVMFromTemplate 从模板创建虚拟机\n"
        "3. 查询虚拟机: 使用 describeVMs 查看已创建的虚拟机\n\n"
        "**创建流程**:\n"
        "- describeTemplates -> 选择模板\n"
        "- describeClusters -> 选择集群\n"
        "- createVMFromTemplate -> 创建虚拟机\n\n"
        "**错误处理**: 所有工具返回统一的 MCPResult 格式，失败时包含错误类型、建议和相关工具推荐。"
    ),
    host=os.getenv("SERVER_HOST", "0.0.0.0"),
    port=int(os.getenv("SERVER_PORT", "8000"))
)


# =============================================================================
# 服务器运行函数
# =============================================================================
def run_server():
    """运行 MCP 服务器"""
    log_level_str = os.getenv("LOG_LEVEL", "INFO").upper()
    logging.basicConfig(
        level=getattr(logging, log_level_str, logging.INFO),
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    logger.info(f"启动 vSphere MCP 服务器，日志级别: {log_level_str}")

    # 检查依赖
    if not PYVMOMI_AVAILABLE:
        logger.warning("pyvmomi 未安装，部分功能将不可用。请运行: pip install pyvmomi")

    transport = os.getenv('SERVER_TRANSPORT', 'stdio')
    logger.info(f"使用传输协议: {transport}")

    mcp.run(transport=transport)


if __name__ == "__main__":
    run_server()
