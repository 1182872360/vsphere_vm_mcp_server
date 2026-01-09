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
    validate_cpu_memory,
)


logger = logging.getLogger(__name__)


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
        cpu=cpu,
        memory_mb=memory_mb
    )
    
    if error:
        return MCPResult(success=False, error=error)
    
    return MCPResult(
        success=True,
        data={
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
        },
        request_id=task_id
    )
