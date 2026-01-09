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
    resource_pool_name: Optional[str] = Field(default=None, description="资源池名称"),
    # Advanced Customization
    ip_address: Optional[str] = Field(default=None, description="静态 IP 地址 (不填则默认 DHCP)"),
    subnet_mask: Optional[str] = Field(default=None, description="子网掩码 (默认 255.255.255.0)"),
    gateway: Optional[str] = Field(default=None, description="默认网关"),
    dns_servers: Optional[list[str]] = Field(default=None, description="DNS 服务器列表"),
    hostname: Optional[str] = Field(default=None, description="主机名 (不填则使用虚拟机名称)"),
    password: Optional[str] = Field(default=None, description="操作系统管理员/Root 密码"),
    domain: Optional[str] = Field(default=None, description="域名 (Linux) 或加入的域 (Windows)")
) -> MCPResult:
    """
    从模板创建虚拟机 (支持自定义 CPU、内存、网络及 Guest OS 配置)

    注意：创建虚拟机前，请确保已准备好以下资源：
    1. 虚拟机名称 (vm_name) - 必须唯一
    2. 模板名称 (template_name) - 可通过 describeTemplates 查询
    3. 集群名称 (cluster_name) - 可通过 describeClusters 查询
    
    高级自定义 (Guest Customization):
    - 如果提供 `ip_address`，则配置静态 IP (推荐同时提供 subnet/gateway)。
    - 如果提供 `password`，将设置为系统管理员/Root 密码。
    - 自定义过程发生在首次启动时，可能需要几分钟。
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
        memory_mb=memory_mb,
        # Customization
        ip_address=ip_address,
        subnet_mask=subnet_mask,
        gateway=gateway,
        dns_servers=dns_servers,
        hostname=hostname,
        password=password,
        domain=domain
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
    
    if any([ip_address, hostname, password]):
        result_data["details"]["customization"] = "enabled"
        if ip_address:
             result_data["details"]["ip"] = ip_address
    
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
