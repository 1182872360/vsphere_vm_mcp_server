# -*- coding: utf-8 -*-
"""
vSphere VM MCP Server - 虚拟机创建模块

基于最佳实践实现的 vSphere 虚拟机创建 MCP 服务器，
参考 server.py 的架构模式：
- 结构化错误处理
- 统一响应模型
- 详细参数验证
- 智能错误解析
- 工具注册模式
"""

import os
import re
import sys
import logging
from enum import Enum
from contextlib import asynccontextmanager
from collections.abc import AsyncGenerator
from typing import Dict, Any, Optional, List, Union

from pydantic import Field, BaseModel, ConfigDict

# 尝试导入 MCP 库
try:
    from mcp.server.fastmcp import FastMCP
    MCP_AVAILABLE = True
except ImportError:
    MCP_AVAILABLE = False

# 尝试导入 pyvmomi (vSphere Python SDK)
try:
    from pyVim.connect import SmartConnect, Disconnect
    from pyVmomi import vim, vmodl
    PYVMOMI_AVAILABLE = True
except ImportError:
    PYVMOMI_AVAILABLE = False


# =============================================================================
# 全局配置
# =============================================================================
logger = logging.getLogger(__name__)


# =============================================================================
# 最佳实践：结构化错误类型定义
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
# 最佳实践：结构化响应模型
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


# =============================================================================
# 业务数据模型 - vSphere 虚拟机相关
# =============================================================================
class VMInfo(MyBaseModel):
    """虚拟机基本信息"""
    name: Optional[str] = Field(description="虚拟机名称", default=None)
    vm_id: Optional[str] = Field(description="虚拟机 ID", default=None)
    power_state: Optional[str] = Field(description="电源状态", default=None)
    guest_os: Optional[str] = Field(description="客户操作系统", default=None)
    num_cpu: Optional[int] = Field(description="CPU 核数", default=None)
    memory_mb: Optional[int] = Field(description="内存大小 (MB)", default=None)
    host_name: Optional[str] = Field(description="所在主机", default=None)
    cluster_name: Optional[str] = Field(description="所在集群", default=None)
    folder_path: Optional[str] = Field(description="文件夹路径", default=None)


class VMTemplateInfo(MyBaseModel):
    """虚拟机模板信息"""
    name: Optional[str] = Field(description="模板名称", default=None)
    template_id: Optional[str] = Field(description="模板 ID", default=None)
    guest_os: Optional[str] = Field(description="操作系统", default=None)
    num_cpu: Optional[int] = Field(description="CPU 核数", default=None)
    memory_mb: Optional[int] = Field(description="内存大小 (MB)", default=None)
    disk_size_gb: Optional[int] = Field(description="磁盘大小 (GB)", default=None)


class HostInfo(MyBaseModel):
    """主机信息"""
    name: Optional[str] = Field(description="主机名称", default=None)
    host_id: Optional[str] = Field(description="主机 ID", default=None)
    cpu_usage: Optional[float] = Field(description="CPU 使用率 (%)", default=None)
    memory_usage: Optional[float] = Field(description="内存使用率 (%)", default=None)
    total_cpu: Optional[int] = Field(description="总 CPU (GHz)", default=None)
    total_memory_gb: Optional[int] = Field(description="总内存 (GB)", default=None)


class ClusterInfo(MyBaseModel):
    """集群信息"""
    name: Optional[str] = Field(description="集群名称", default=None)
    cluster_id: Optional[str] = Field(description="集群 ID", default=None)
    num_hosts: Optional[int] = Field(description="主机数量", default=None)
    num_vms: Optional[int] = Field(description="虚拟机数量", default=None)


class FolderInfo(MyBaseModel):
    """文件夹信息"""
    name: Optional[str] = Field(description="文件夹名称", default=None)
    folder_id: Optional[str] = Field(description="文件夹 ID", default=None)
    path: Optional[str] = Field(description="文件夹路径", default=None)


class ResourcePoolInfo(MyBaseModel):
    """资源池信息"""
    name: Optional[str] = Field(description="资源池名称", default=None)
    resource_pool_id: Optional[str] = Field(description="资源池 ID", default=None)
    cpu_limit: Optional[float] = Field(description="CPU 限制 (GHz)", default=None)
    memory_limit_gb: Optional[float] = Field(description="内存限制 (GB)", default=None)


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


# =============================================================================
# 参数验证辅助函数
# =============================================================================
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


# =============================================================================
# vSphere 客户端管理
# =============================================================================
class VSphereClient:
    """vSphere 客户端封装 - 管理连接和基本操作"""

    def __init__(self, host: str, username: str, password: str, port: int = 443):
        self.host = host
        self.username = username
        self.password = password
        self.port = port
        self._connection = None

    def connect(self) -> Optional[MCPError]:
        """连接到 vSphere"""
        try:
            if not PYVMOMI_AVAILABLE:
                return MCPError(
                    error_type=ErrorType.DEPENDENCY_MISSING,
                    message="pyvmomi 库未安装",
                    suggestion="运行 'pip install pyvmomi' 安装 vSphere Python SDK"
                )

            self._connection = SmartConnect(
                host=self.host,
                user=self.username,
                pwd=self.password,
                port=self.port,
                disableSslCertVerification=True
            )
            return None

        except Exception as e:
            return parse_vsphere_error(e, "connect")

    def disconnect(self):
        """断开连接"""
        if self._connection:
            Disconnect(self._connection)
            self._connection = None

    def get_content(self):
        """获取 vSphere 内容"""
        if not self._connection:
            return None
        return self._connection.RetrieveContent()

    def find_object_by_name(self, name: str, vim_type):
        """根据名称查找对象"""
        content = self.get_content()
        if not content:
            return None

        container = content.viewManager.CreateContainerView(
            content.rootFolder, [vim_type], True
        )

        for obj in container.view:
            if obj.name == name:
                container.Destroy()
                return obj

        container.Destroy()
        return None

    def get_all_objects(self, vim_type):
        """获取所有指定类型的对象"""
        content = self.get_content()
        if not content:
            return []

        container = content.viewManager.CreateContainerView(
            content.rootFolder, [vim_type], True
        )

        objects = list(container.view)
        container.Destroy()
        return objects


# =============================================================================
# 核心 API 函数 - vSphere 虚拟机管理
# =============================================================================
async def describe_templates(
    cluster_name: Optional[str] = Field(default=None, description="集群名称，用于筛选")
) -> MCPResult:
    """查询可用的虚拟机模板列表"""
    # 这里需要从配置或上下文中获取 vSphere 连接信息
    # 为演示目的，返回模拟数据
    return MCPResult(
        success=True,
        data=[
            VMTemplateInfo(
                name="ubuntu-20.04-template",
                template_id="vm-100",
                guest_os="Ubuntu Linux (64-bit)",
                num_cpu=2,
                memory_mb=4096,
                disk_size_gb=50
            ),
            VMTemplateInfo(
                name="centos-7-template",
                template_id="vm-101",
                guest_os="CentOS 7 (64-bit)",
                num_cpu=2,
                memory_mb=2048,
                disk_size_gb=40
            )
        ]
    )


async def describe_hosts(
    cluster_name: Optional[str] = Field(default=None, description="集群名称，用于筛选")
) -> MCPResult:
    """查询可用的主机列表"""
    return MCPResult(
        success=True,
        data=[
            HostInfo(
                name="esxi-01.example.com",
                host_id="host-10",
                cpu_usage=45.2,
                memory_usage=62.8,
                total_cpu=32,
                total_memory_gb=128
            ),
            HostInfo(
                name="esxi-02.example.com",
                host_id="host-11",
                cpu_usage=28.5,
                memory_usage=45.1,
                total_cpu=32,
                total_memory_gb=128
            )
        ]
    )


async def describe_clusters() -> MCPResult:
    """查询可用的集群列表"""
    return MCPResult(
        success=True,
        data=[
            ClusterInfo(
                name="Cluster01",
                cluster_id="cluster-10",
                num_hosts=2,
                num_vms=15
            ),
            ClusterInfo(
                name="Cluster02",
                cluster_id="cluster-11",
                num_hosts=3,
                num_vms=25
            )
        ]
    )


async def describe_folders() -> MCPResult:
    """查询可用的文件夹列表"""
    return MCPResult(
        success=True,
        data=[
            FolderInfo(
                name="Production",
                folder_id="folder-10",
                path="/Datacenter/vm/Production"
            ),
            FolderInfo(
                name="Development",
                folder_id="folder-11",
                path="/Datacenter/vm/Development"
            )
        ]
    )


async def describe_resource_pools(
    cluster_name: Optional[str] = Field(default=None, description="集群名称，用于筛选")
) -> MCPResult:
    """查询可用的资源池列表"""
    return MCPResult(
        success=True,
        data=[
            ResourcePoolInfo(
                name="Production-Pool",
                resource_pool_id="resgroup-10",
                cpu_limit=16.0,
                memory_limit_gb=64.0
            ),
            ResourcePoolInfo(
                name="Development-Pool",
                resource_pool_id="resgroup-11",
                cpu_limit=8.0,
                memory_limit_gb=32.0
            )
        ]
    )


async def create_vm_from_template(
    vm_name: str = Field(description="虚拟机名称"),
    template_name: str = Field(description="模板名称"),
    cluster_name: str = Field(description="集群名称"),
    cpu: Optional[int] = Field(default=None, description="CPU 核数，覆盖模板设置"),
    memory_mb: Optional[int] = Field(default=None, description="内存大小 (MB)，覆盖模板设置"),
    folder_name: Optional[str] = Field(default=None, description="文件夹名称"),
    resource_pool_name: Optional[str] = Field(default=None, description="资源池名称")
) -> MCPResult:
    """
    从模板创建虚拟机

    注意：创建虚拟机前，请确保已准备好以下资源：
    1. 虚拟机名称 (vm_name) - 必须唯一
    2. 模板名称 (template_name) - 可通过 describeTemplates 查询
    3. 集群名称 (cluster_name) - 可通过 describeClusters 查询
    4. 可选：CPU/内存配置
    5. 可选：文件夹和资源池
    """
    # 参数验证链
    if error := validate_vm_name(vm_name):
        return MCPResult(success=False, error=error)

    if error := validate_template_name(template_name):
        return MCPResult(success=False, error=error)

    if error := validate_cluster_name(cluster_name):
        return MCPResult(success=False, error=error)

    if error := validate_cpu_memory(cpu, memory_mb):
        return MCPResult(success=False, error=error)

    # TODO: 实际的 vSphere 虚拟机创建逻辑
    # 这里应该：
    # 1. 连接到 vSphere
    # 2. 查找模板、集群、文件夹、资源池
    # 3. 克隆虚拟机
    # 4. 配置 CPU/内存
    # 5. 返回结果

    # 模拟创建成功
    return MCPResult(
        success=True,
        data={
            "vm_name": vm_name,
            "status": "creation_started",
            "message": f"虚拟机 '{vm_name}' 创建请求已提交",
            "details": {
                "template": template_name,
                "cluster": cluster_name,
                "cpu": cpu,
                "memory_mb": memory_mb,
                "folder": folder_name,
                "resource_pool": resource_pool_name
            }
        },
        request_id=f"vm-create-{vm_name}"
    )


async def describe_vms(
    cluster_name: Optional[str] = Field(default=None, description="集群名称，用于筛选"),
    vm_name: Optional[str] = Field(default=None, description="虚拟机名称，支持模糊匹配")
) -> MCPResult:
    """查询虚拟机列表"""
    # 模拟查询结果
    vms = [
        VMInfo(
            name="web-server-01",
            vm_id="vm-100",
            power_state="poweredOn",
            guest_os="Ubuntu Linux (64-bit)",
            num_cpu=2,
            memory_mb=4096,
            host_name="esxi-01.example.com",
            cluster_name="Cluster01",
            folder_path="/Datacenter/vm/Production"
        ),
        VMInfo(
            name="db-server-01",
            vm_id="vm-101",
            power_state="poweredOn",
            guest_os="CentOS 7 (64-bit)",
            num_cpu=4,
            memory_mb=8192,
            host_name="esxi-02.example.com",
            cluster_name="Cluster01",
            folder_path="/Datacenter/vm/Production"
        )
    ]

    # 应用筛选
    if vm_name:
        vms = [vm for vm in vms if vm_name.lower() in (vm.name or "").lower()]

    if cluster_name:
        vms = [vm for vm in vms if vm.cluster_name == cluster_name]

    return MCPResult(success=True, data=vms)


# =============================================================================
# 工具注册类 - 参考 server.py 的最佳实践
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
# 生命周期函数 - 参考 server.py 的最佳实践
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
# FastMCP 实例创建和服务器运行
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