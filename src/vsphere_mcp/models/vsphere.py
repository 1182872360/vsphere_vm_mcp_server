# -*- coding: utf-8 -*-
"""
vSphere MCP Server - vSphere 业务数据模型
"""

from typing import Optional, List

from pydantic import Field

from .base import MyBaseModel


# =============================================================================
# 虚拟机相关模型
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


# =============================================================================
# 基础设施模型
# =============================================================================
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


class NetworkInfo(MyBaseModel):
    """网络信息"""
    name: Optional[str] = Field(description="网络名称", default=None)
    network_id: Optional[str] = Field(description="网络 ID", default=None)
    network_type: Optional[str] = Field(description="网络类型 (Standard/Distributed)", default=None)
