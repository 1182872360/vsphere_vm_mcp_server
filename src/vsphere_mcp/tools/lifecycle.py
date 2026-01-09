# -*- coding: utf-8 -*-
"""
vSphere MCP Server - 生命周期管理工具
"""

import logging
from typing import Optional

from pydantic import Field

from ..models import MCPResult
from ..client import get_vsphere_client
from ..utils import (
    validate_vm_name,
    validate_template_name,
    validate_cluster_name,
    validate_network_name,
    validate_cpu_memory,
)


logger = logging.getLogger(__name__)


async def create_vm_from_template(
    vm_name: str = Field(description="虚拟机名称"),
    template_name: str = Field(description="模板名称"),
    cluster_name: str = Field(description="集群名称"),
    cpu: Optional[int] = Field(default=None, description="CPU 核数，覆盖模板设置"),
    memory_mb: Optional[int] = Field(default=None, description="内存大小 (MB)，覆盖模板设置"),
    network_name: Optional[str] = Field(default=None, description="网络名称，覆盖模板默认网络"),
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
    5. 可选：网络配置 (network_name) - 可通过 describeNetworks 查询
    6. 可选：文件夹和资源池
    """
    # 参数验证链
    if error := validate_vm_name(vm_name):
        return MCPResult(success=False, error=error)

    if error := validate_template_name(template_name):
        return MCPResult(success=False, error=error)

    if error := validate_cluster_name(cluster_name):
        return MCPResult(success=False, error=error)
        
    if error := validate_network_name(network_name):
        return MCPResult(success=False, error=error)

    if error := validate_cpu_memory(cpu, memory_mb):
        return MCPResult(success=False, error=error)

    # 获取 vSphere 客户端
    client, error = get_vsphere_client()
    if error:
        return MCPResult(success=False, error=error)
    
    # 执行克隆
    task_id, error = client.clone_vm(
        template_name=template_name,
        vm_name=vm_name,
        cluster_name=cluster_name,
        folder_name=folder_name,
        resource_pool_name=resource_pool_name,
        network_name=network_name,
        cpu=cpu,
        memory_mb=memory_mb
    )
    
    if error:
        return MCPResult(success=False, error=error)
    
    result_data = {
        "vm_name": vm_name,
        "status": "creation_started",
        "message": f"虚拟机 '{vm_name}' 创建请求已提交",
        "task_id": task_id,
        "details": {
            "template": template_name,
            "cluster": cluster_name,
            "cpu": cpu,
            "memory_mb": memory_mb,
            "folder": folder_name,
            "resource_pool": resource_pool_name
        }
    }
    
    if network_name:
        result_data["details"]["network"] = network_name
    
    return MCPResult(
        success=True,
        data=result_data,
        request_id=task_id
    )


async def reconfigure_vm(
    vm_name: str = Field(description="虚拟机名称"),
    cpu: Optional[int] = Field(default=None, description="新的 CPU 核数"),
    memory_mb: Optional[int] = Field(default=None, description="新的内存大小 (MB)"),
    disk_size_gb: Optional[int] = Field(default=None, description="新的磁盘大小 (GB)，仅允许扩容"),
    network_name: Optional[str] = Field(default=None, description="新的网络名称 (修改第一块网卡)")
) -> MCPResult:
    """
    重新配置虚拟机 (修改 CPU/内存/磁盘/网络)

    注意：
    1. 虚拟机必须处于 **关机状态** (Powered Off) 才能进行变更。
    2. 磁盘仅支持 **扩容** (Increase Size)，不支持缩容。
    3. 至少指定一项配置变更。
    """
    # 参数验证
    pass  # Pydantic has validated types, logical validation below

    if all(arg is None for arg in [cpu, memory_mb, disk_size_gb, network_name]):
        return MCPResult(
            success=False, 
            error="Please specify at least one configuration to change: cpu, memory_mb, disk_size_gb, or network_name"
        )

    if error := validate_cpu_memory(cpu, memory_mb):
        return MCPResult(success=False, error=error)

    # 获取客户端
    client, error = get_vsphere_client()
    if error:
        return MCPResult(success=False, error=error)

    # 执行重新配置
    task_id, error = client.reconfigure_vm(
        vm_name=vm_name,
        cpu=cpu,
        memory_mb=memory_mb,
        disk_size_gb=disk_size_gb,
        network_name=network_name
    )

    if error:
        return MCPResult(success=False, error=error)

    result_data = {
        "vm_name": vm_name,
        "status": "reconfiguration_started",
        "message": f"虚拟机 '{vm_name}' 配置更新请求已提交",
        "task_id": task_id,
        "details": {}
    }

    if cpu:
        result_data["details"]["cpu"] = cpu
    if memory_mb:
        result_data["details"]["memory_mb"] = memory_mb
    if disk_size_gb:
        result_data["details"]["disk_size_gb"] = disk_size_gb
    if network_name:
        result_data["details"]["network_name"] = network_name

    return MCPResult(
        success=True,
        data=result_data,
        request_id=task_id
    )
