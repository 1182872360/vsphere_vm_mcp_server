# -*- coding: utf-8 -*-
"""
vSphere MCP Server - 查询类工具
"""

import logging
from typing import Optional

from pydantic import Field

from ..models import MCPResult
from ..client import get_vsphere_client
from ..utils import parse_vsphere_error


logger = logging.getLogger(__name__)


async def describe_templates(
    cluster_name: Optional[str] = Field(default=None, description="集群名称，用于筛选")
) -> MCPResult:
    """查询可用的虚拟机模板列表"""
    client, error = get_vsphere_client()
    if error:
        return MCPResult(success=False, error=error)
    
    try:
        templates = client.get_templates(cluster_name)
        return MCPResult(success=True, data=templates)
    except Exception as e:
        logger.error(f"查询模板列表失败: {e}")
        return MCPResult(success=False, error=parse_vsphere_error(e, "describe_templates"))


async def describe_hosts(
    cluster_name: Optional[str] = Field(default=None, description="集群名称，用于筛选")
) -> MCPResult:
    """查询可用的主机列表"""
    client, error = get_vsphere_client()
    if error:
        return MCPResult(success=False, error=error)
    
    try:
        hosts = client.get_hosts(cluster_name)
        return MCPResult(success=True, data=hosts)
    except Exception as e:
        logger.error(f"查询主机列表失败: {e}")
        return MCPResult(success=False, error=parse_vsphere_error(e, "describe_hosts"))


async def describe_clusters() -> MCPResult:
    """查询可用的集群列表"""
    client, error = get_vsphere_client()
    if error:
        return MCPResult(success=False, error=error)
    
    try:
        clusters = client.get_clusters()
        return MCPResult(success=True, data=clusters)
    except Exception as e:
        logger.error(f"查询集群列表失败: {e}")
        return MCPResult(success=False, error=parse_vsphere_error(e, "describe_clusters"))


async def describe_folders() -> MCPResult:
    """查询可用的文件夹列表"""
    client, error = get_vsphere_client()
    if error:
        return MCPResult(success=False, error=error)
    
    try:
        folders = client.get_folders()
        return MCPResult(success=True, data=folders)
    except Exception as e:
        logger.error(f"查询文件夹列表失败: {e}")
        return MCPResult(success=False, error=parse_vsphere_error(e, "describe_folders"))


async def describe_resource_pools(
    cluster_name: Optional[str] = Field(default=None, description="集群名称，用于筛选")
) -> MCPResult:
    """查询可用的资源池列表"""
    client, error = get_vsphere_client()
    if error:
        return MCPResult(success=False, error=error)
    
    try:
        pools = client.get_resource_pools(cluster_name)
        return MCPResult(success=True, data=pools)
    except Exception as e:
        logger.error(f"查询资源池列表失败: {e}")
        return MCPResult(success=False, error=parse_vsphere_error(e, "describe_resource_pools"))


async def describe_networks(
    cluster_name: Optional[str] = Field(default=None, description="集群名称，用于筛选（注：网络通常跨集群，筛选仅供参考）")
) -> MCPResult:
    """查询可用的网络列表"""
    client, error = get_vsphere_client()
    if error:
        return MCPResult(success=False, error=error)
    
    try:
        networks = client.get_networks(cluster_name)
        return MCPResult(success=True, data=networks)
    except Exception as e:
        logger.error(f"查询网络列表失败: {e}")
        return MCPResult(success=False, error=parse_vsphere_error(e, "describe_networks"))


async def describe_vms(
    cluster_name: Optional[str] = Field(default=None, description="集群名称，用于筛选"),
    vm_name: Optional[str] = Field(default=None, description="虚拟机名称，支持模糊匹配")
) -> MCPResult:
    """查询虚拟机列表"""
    client, error = get_vsphere_client()
    if error:
        return MCPResult(success=False, error=error)
    
    try:
        vms = client.get_virtual_machines(cluster_name, vm_name)
        return MCPResult(success=True, data=vms)
    except Exception as e:
        logger.error(f"查询虚拟机列表失败: {e}")
        return MCPResult(success=False, error=parse_vsphere_error(e, "describe_vms"))


async def get_vm_power_state(
    vm_name: str = Field(description="虚拟机名称")
) -> MCPResult:
    """查询虚拟机的电源状态 (poweredOn/poweredOff/suspended)"""
    client, error = get_vsphere_client()
    if error:
        return MCPResult(success=False, error=error)
    
    state, error = client.get_vm_power_state(vm_name)
    if error:
        return MCPResult(success=False, error=error)
    
    return MCPResult(
        success=True, 
        data={
            "vm_name": vm_name,
            "power_state": state,
            "can_reconfigure": state == "poweredOff"
        }
    )
