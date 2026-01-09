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
import sys
import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from mcp.server.fastmcp import FastMCP

from .client import PYVMOMI_AVAILABLE
from .tools import (
    describe_templates,
    describe_hosts,
    describe_clusters,
    describe_folders,
    describe_resource_pools,
    describe_networks,
    describe_vms,
    create_vm_from_template,
)


# 配置日志
logging.basicConfig(
    level=getattr(logging, os.getenv("LOG_LEVEL", "INFO")),
    format='[%(asctime)s] %(levelname)-8s %(message)s             %(filename)s:%(lineno)d',
    datefmt='%y/%m/%d %H:%M:%S'
)
logger = logging.getLogger(__name__)


class ToolRegistry:
    """工具注册中心 - 负责将工具函数注册到 MCP 服务器"""

    def __init__(self, mcp_instance: FastMCP):
        self.mcp = mcp_instance

    def register_tools(self):
        """注册所有工具"""
        self._register_query_tools()
        self._register_lifecycle_tools()
        logger.info("所有工具注册完成")
        return self.mcp

    def _register_query_tools(self):
        """注册查询类工具"""
        self.mcp.tool(
            name="describeTemplates",
            description="查询可用的虚拟机模板列表",
            annotations={"title": "查询虚拟机模板", "readOnlyHint": True}
        )(describe_templates)

        self.mcp.tool(
            name="describeHosts",
            description="查询可用的 ESXi 主机列表",
            annotations={"title": "查询主机", "readOnlyHint": True}
        )(describe_hosts)

        self.mcp.tool(
            name="describeClusters",
            description="查询可用的集群列表",
            annotations={"title": "查询集群", "readOnlyHint": True}
        )(describe_clusters)

        self.mcp.tool(
            name="describeFolders",
            description="查询可用的虚拟机文件夹列表",
            annotations={"title": "查询文件夹", "readOnlyHint": True}
        )(describe_folders)

        self.mcp.tool(
            name="describeResourcePools",
            description="查询可用的资源池列表",
            annotations={"title": "查询资源池", "readOnlyHint": True}
        )(describe_resource_pools)
        
        self.mcp.tool(
            name="describeNetworks",
            description="查询可用的网络列表",
            annotations={"title": "查询网络", "readOnlyHint": True}
        )(describe_networks)

        self.mcp.tool(
            name="describeVMs",
            description="查询虚拟机列表 (支持按名称或集群筛选)",
            annotations={"title": "查询虚拟机", "readOnlyHint": True}
        )(describe_vms)

    def _register_lifecycle_tools(self):
        """注册生命周期管理工具"""
        self.mcp.tool(
            name="createVMFromTemplate",
            description="从模板创建虚拟机 (支持自定义 CPU、内存、网络)",
            annotations={"title": "创建虚拟机 (从模板)", "readOnlyHint": False, "destructiveHint": False}
        )(create_vm_from_template)


@asynccontextmanager
async def lifespan(server: FastMCP) -> AsyncGenerator[None, None]:
    """MCP Server 生命周期管理"""
    logger.info("初始化 vSphere MCP Server...")

    # 检查依赖
    if not PYVMOMI_AVAILABLE:
        logger.error("错误: 未安装 pyvmomi 库。请运行 'pip install pyvmomi'")
    
    # 在启动时打印配置通过
    host = os.getenv("VSPHERE_HOST")
    logger.info(f"vSphere 配置: {host if host else '未设置 (将在首次调用时检查)'}")

    # 注册工具
    registry = ToolRegistry(server)
    registry.register_tools()

    yield

    logger.info("关闭 vSphere MCP Server...")


# 创建 MCP 服务器实例
mcp = FastMCP(
    "vSphere VM Manager",
    lifespan=lifespan,
    dependencies=["pyvmomi", "pydantic"]
)


def run_server():
    """运行服务器"""
    import argparse
    
    parser = argparse.ArgumentParser(description="vSphere MCP Server")
    parser.add_argument("--port", type=int, default=int(os.getenv("SERVER_PORT", "8000")), help="SSE 传输模式的端口")
    parser.add_argument("--transport", type=str, default=os.getenv("SERVER_TRANSPORT", "stdio"), choices=["stdio", "sse"], help="传输模式 (stdio/sse)")
    
    args = parser.parse_args()
    
    logger.info(f"启动 vSphere MCP 服务器，日志级别: {logging.getLevelName(logger.getEffectiveLevel())}")
    
    # 根据传输模式运行
    transport = args.transport
    logger.info(f"使用传输协议: {transport}")
    
    if transport == "sse":
        mcp.run(transport="sse", port=args.port, host=os.getenv("SERVER_HOST", "0.0.0.0"))
    else:
        mcp.run(transport="stdio")


if __name__ == "__main__":
    run_server()
