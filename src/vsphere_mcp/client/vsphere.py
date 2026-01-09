# -*- coding: utf-8 -*-
"""
vSphere MCP Server - vSphere 客户端模块

封装与 vSphere/vCenter 的所有交互
"""

import os
import logging
from typing import Optional, List, Tuple

# 尝试导入 pyvmomi (vSphere Python SDK)
try:
    from pyVim.connect import SmartConnect, Disconnect
    from pyVmomi import vim, vmodl
    PYVMOMI_AVAILABLE = True
except ImportError:
    PYVMOMI_AVAILABLE = False
    vim = None  # type: ignore

from ..models import (
    ErrorType,
    MCPError,
    VMInfo,
    VMTemplateInfo,
    HostInfo,
    ClusterInfo,
    FolderInfo,
    ResourcePoolInfo,
)
from ..utils.errors import (
    TOOL_DESCRIBE_TEMPLATES,
    TOOL_DESCRIBE_CLUSTERS,
    TOOL_DESCRIBE_FOLDERS,
    TOOL_DESCRIBE_RESOURCE_POOLS,
    parse_vsphere_error,
)


logger = logging.getLogger(__name__)


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

    def is_connected(self) -> bool:
        """检查是否已连接"""
        return self._connection is not None

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

    # =========================================================================
    # 扩展的查询方法
    # =========================================================================
    def get_templates(self, cluster_name: Optional[str] = None) -> List[VMTemplateInfo]:
        """获取所有虚拟机模板"""
        templates = []
        vms = self.get_all_objects(vim.VirtualMachine)
        
        for vm in vms:
            try:
                if not vm.config or not vm.config.template:
                    continue
                
                # 如果指定了集群，进行筛选
                if cluster_name:
                    vm_cluster = self._get_vm_cluster(vm)
                    if vm_cluster and vm_cluster.name != cluster_name:
                        continue
                
                # 计算磁盘大小
                disk_size_gb = 0
                if vm.config.hardware and vm.config.hardware.device:
                    for device in vm.config.hardware.device:
                        if isinstance(device, vim.vm.device.VirtualDisk):
                            disk_size_gb += device.capacityInKB // (1024 * 1024)
                
                templates.append(VMTemplateInfo(
                    name=vm.name,
                    template_id=vm._moId,
                    guest_os=vm.config.guestFullName if vm.config else None,
                    num_cpu=vm.config.hardware.numCPU if vm.config and vm.config.hardware else None,
                    memory_mb=vm.config.hardware.memoryMB if vm.config and vm.config.hardware else None,
                    disk_size_gb=disk_size_gb if disk_size_gb > 0 else None
                ))
            except Exception as e:
                logger.warning(f"获取模板 {vm.name} 信息失败: {e}")
                continue
        
        return templates

    def get_hosts(self, cluster_name: Optional[str] = None) -> List[HostInfo]:
        """获取所有 ESXi 主机"""
        hosts = []
        host_systems = self.get_all_objects(vim.HostSystem)
        
        for host in host_systems:
            try:
                # 如果指定了集群，进行筛选
                if cluster_name:
                    host_cluster = self._get_host_cluster(host)
                    if host_cluster and host_cluster.name != cluster_name:
                        continue
                
                # 计算资源使用情况
                cpu_usage = None
                memory_usage = None
                total_cpu = None
                total_memory_gb = None
                
                if host.summary and host.summary.hardware:
                    hw = host.summary.hardware
                    total_cpu = hw.numCpuCores
                    total_memory_gb = hw.memorySize // (1024 ** 3)
                
                if host.summary and host.summary.quickStats:
                    stats = host.summary.quickStats
                    if total_cpu and hw.cpuMhz:
                        total_cpu_mhz = total_cpu * hw.cpuMhz
                        cpu_usage = round((stats.overallCpuUsage / total_cpu_mhz) * 100, 1) if total_cpu_mhz > 0 else 0
                    if host.summary.hardware.memorySize:
                        memory_usage = round((stats.overallMemoryUsage * 1024 * 1024 / host.summary.hardware.memorySize) * 100, 1)
                
                hosts.append(HostInfo(
                    name=host.name,
                    host_id=host._moId,
                    cpu_usage=cpu_usage,
                    memory_usage=memory_usage,
                    total_cpu=total_cpu,
                    total_memory_gb=total_memory_gb
                ))
            except Exception as e:
                logger.warning(f"获取主机 {host.name} 信息失败: {e}")
                continue
        
        return hosts

    def get_clusters(self) -> List[ClusterInfo]:
        """获取所有集群"""
        clusters = []
        cluster_objs = self.get_all_objects(vim.ClusterComputeResource)
        
        for cluster in cluster_objs:
            try:
                num_hosts = len(cluster.host) if cluster.host else 0
                
                # 统计虚拟机数量
                num_vms = 0
                if cluster.resourcePool:
                    num_vms = self._count_vms_in_resource_pool(cluster.resourcePool)
                
                clusters.append(ClusterInfo(
                    name=cluster.name,
                    cluster_id=cluster._moId,
                    num_hosts=num_hosts,
                    num_vms=num_vms
                ))
            except Exception as e:
                logger.warning(f"获取集群 {cluster.name} 信息失败: {e}")
                continue
        
        return clusters

    def get_folders(self) -> List[FolderInfo]:
        """获取所有 VM 文件夹"""
        folders = []
        folder_objs = self.get_all_objects(vim.Folder)
        
        for folder in folder_objs:
            try:
                # 只返回 VM 文件夹（排除主机、网络、数据存储文件夹）
                if not self._is_vm_folder(folder):
                    continue
                
                path = self._get_folder_path(folder)
                
                folders.append(FolderInfo(
                    name=folder.name,
                    folder_id=folder._moId,
                    path=path
                ))
            except Exception as e:
                logger.warning(f"获取文件夹 {folder.name} 信息失败: {e}")
                continue
        
        return folders

    def get_resource_pools(self, cluster_name: Optional[str] = None) -> List[ResourcePoolInfo]:
        """获取所有资源池"""
        pools = []
        pool_objs = self.get_all_objects(vim.ResourcePool)
        
        for pool in pool_objs:
            try:
                # 如果指定了集群，进行筛选
                if cluster_name:
                    pool_cluster = self._get_resource_pool_cluster(pool)
                    if pool_cluster and pool_cluster.name != cluster_name:
                        continue
                
                cpu_limit = None
                memory_limit_gb = None
                
                if pool.config and pool.config.cpuAllocation:
                    limit = pool.config.cpuAllocation.limit
                    if limit and limit > 0:
                        cpu_limit = limit / 1000.0  # MHz to GHz
                
                if pool.config and pool.config.memoryAllocation:
                    limit = pool.config.memoryAllocation.limit
                    if limit and limit > 0:
                        memory_limit_gb = limit / 1024.0  # MB to GB
                
                pools.append(ResourcePoolInfo(
                    name=pool.name,
                    resource_pool_id=pool._moId,
                    cpu_limit=cpu_limit,
                    memory_limit_gb=memory_limit_gb
                ))
            except Exception as e:
                logger.warning(f"获取资源池 {pool.name} 信息失败: {e}")
                continue
        
        return pools

    def get_virtual_machines(self, cluster_name: Optional[str] = None, vm_name_filter: Optional[str] = None) -> List[VMInfo]:
        """获取所有虚拟机（非模板）"""
        vms_info = []
        vms = self.get_all_objects(vim.VirtualMachine)
        
        for vm in vms:
            try:
                # 跳过模板
                if vm.config and vm.config.template:
                    continue
                
                # 名称筛选
                if vm_name_filter and vm_name_filter.lower() not in vm.name.lower():
                    continue
                
                # 集群筛选
                vm_cluster = self._get_vm_cluster(vm)
                if cluster_name and vm_cluster and vm_cluster.name != cluster_name:
                    continue
                
                # 获取主机名
                host_name = None
                if vm.runtime and vm.runtime.host:
                    host_name = vm.runtime.host.name
                
                # 获取文件夹路径
                folder_path = None
                if vm.parent:
                    folder_path = self._get_folder_path(vm.parent)
                
                vms_info.append(VMInfo(
                    name=vm.name,
                    vm_id=vm._moId,
                    power_state=str(vm.runtime.powerState) if vm.runtime else None,
                    guest_os=vm.config.guestFullName if vm.config else None,
                    num_cpu=vm.config.hardware.numCPU if vm.config and vm.config.hardware else None,
                    memory_mb=vm.config.hardware.memoryMB if vm.config and vm.config.hardware else None,
                    host_name=host_name,
                    cluster_name=vm_cluster.name if vm_cluster else None,
                    folder_path=folder_path
                ))
            except Exception as e:
                logger.warning(f"获取虚拟机 {vm.name} 信息失败: {e}")
                continue
        
        return vms_info

    def clone_vm(
        self,
        template_name: str,
        vm_name: str,
        cluster_name: str,
        folder_name: Optional[str] = None,
        resource_pool_name: Optional[str] = None,
        cpu: Optional[int] = None,
        memory_mb: Optional[int] = None
    ) -> Tuple[Optional[str], Optional[MCPError]]:
        """从模板克隆虚拟机"""
        try:
            # 查找模板
            template = self.find_object_by_name(template_name, vim.VirtualMachine)
            if not template:
                return None, MCPError(
                    error_type=ErrorType.RESOURCE_NOT_FOUND,
                    parameter="template_name",
                    message=f"模板 '{template_name}' 不存在",
                    suggestion="请使用 describeTemplates 查询可用模板",
                    related_tools=[TOOL_DESCRIBE_TEMPLATES]
                )
            
            # 查找集群
            cluster = self.find_object_by_name(cluster_name, vim.ClusterComputeResource)
            if not cluster:
                return None, MCPError(
                    error_type=ErrorType.RESOURCE_NOT_FOUND,
                    parameter="cluster_name",
                    message=f"集群 '{cluster_name}' 不存在",
                    suggestion="请使用 describeClusters 查询可用集群",
                    related_tools=[TOOL_DESCRIBE_CLUSTERS]
                )
            
            # 确定资源池
            resource_pool = None
            if resource_pool_name:
                resource_pool = self.find_object_by_name(resource_pool_name, vim.ResourcePool)
                if not resource_pool:
                    return None, MCPError(
                        error_type=ErrorType.RESOURCE_NOT_FOUND,
                        parameter="resource_pool_name",
                        message=f"资源池 '{resource_pool_name}' 不存在",
                        suggestion="请使用 describeResourcePools 查询可用资源池",
                        related_tools=[TOOL_DESCRIBE_RESOURCE_POOLS]
                    )
            else:
                resource_pool = cluster.resourcePool
            
            # 确定目标文件夹
            folder = None
            if folder_name:
                folder = self.find_object_by_name(folder_name, vim.Folder)
                if not folder:
                    return None, MCPError(
                        error_type=ErrorType.RESOURCE_NOT_FOUND,
                        parameter="folder_name",
                        message=f"文件夹 '{folder_name}' 不存在",
                        suggestion="请使用 describeFolders 查询可用文件夹",
                        related_tools=[TOOL_DESCRIBE_FOLDERS]
                    )
            else:
                # 使用模板所在的文件夹
                folder = template.parent
            
            # 创建克隆规格
            relocate_spec = vim.vm.RelocateSpec()
            relocate_spec.pool = resource_pool
            
            clone_spec = vim.vm.CloneSpec()
            clone_spec.location = relocate_spec
            clone_spec.powerOn = False
            clone_spec.template = False
            
            # 配置 CPU 和内存
            if cpu or memory_mb:
                config_spec = vim.vm.ConfigSpec()
                if cpu:
                    config_spec.numCPUs = cpu
                if memory_mb:
                    config_spec.memoryMB = memory_mb
                clone_spec.config = config_spec
            
            # 执行克隆
            task = template.Clone(folder=folder, name=vm_name, spec=clone_spec)
            
            return f"task-{task._moId}", None
            
        except Exception as e:
            return None, parse_vsphere_error(e, "clone_vm")

    # =========================================================================
    # 辅助方法
    # =========================================================================
    def _get_vm_cluster(self, vm):
        """获取虚拟机所在的集群"""
        try:
            if vm.runtime and vm.runtime.host:
                host = vm.runtime.host
                if host.parent and isinstance(host.parent, vim.ClusterComputeResource):
                    return host.parent
        except Exception:
            pass
        return None

    def _get_host_cluster(self, host):
        """获取主机所在的集群"""
        try:
            if host.parent and isinstance(host.parent, vim.ClusterComputeResource):
                return host.parent
        except Exception:
            pass
        return None

    def _get_resource_pool_cluster(self, pool):
        """获取资源池所在的集群"""
        try:
            parent = pool.parent
            while parent:
                if isinstance(parent, vim.ClusterComputeResource):
                    return parent
                parent = getattr(parent, 'parent', None)
        except Exception:
            pass
        return None

    def _count_vms_in_resource_pool(self, pool) -> int:
        """统计资源池中的虚拟机数量"""
        count = 0
        try:
            if pool.vm:
                count += len([vm for vm in pool.vm if not (vm.config and vm.config.template)])
            if pool.resourcePool:
                for child_pool in pool.resourcePool:
                    count += self._count_vms_in_resource_pool(child_pool)
        except Exception:
            pass
        return count

    def _is_vm_folder(self, folder) -> bool:
        """检查文件夹是否是 VM 文件夹"""
        try:
            # 检查文件夹类型
            if hasattr(folder, 'childType') and folder.childType:
                return 'VirtualMachine' in folder.childType
        except Exception:
            pass
        return False

    def _get_folder_path(self, folder) -> str:
        """获取文件夹的完整路径"""
        path_parts = []
        current = folder
        try:
            while current and hasattr(current, 'name'):
                if isinstance(current, vim.Datacenter):
                    path_parts.append(current.name)
                    break
                path_parts.append(current.name)
                current = getattr(current, 'parent', None)
        except Exception:
            pass
        
        path_parts.reverse()
        return "/" + "/".join(path_parts) if path_parts else "/"


# =============================================================================
# 全局客户端管理
# =============================================================================
_vsphere_client: Optional[VSphereClient] = None


def get_vsphere_client() -> Tuple[Optional[VSphereClient], Optional[MCPError]]:
    """获取全局 vSphere 客户端，自动处理连接"""
    global _vsphere_client
    
    # 检查环境变量
    host = os.getenv("VSPHERE_HOST")
    username = os.getenv("VSPHERE_USERNAME")
    password = os.getenv("VSPHERE_PASSWORD")
    port = int(os.getenv("VSPHERE_PORT", "443"))
    
    if not host or not username or not password:
        return None, MCPError(
            error_type=ErrorType.MISSING_PARAMETER,
            message="vSphere 连接配置不完整",
            suggestion="请设置环境变量: VSPHERE_HOST, VSPHERE_USERNAME, VSPHERE_PASSWORD"
        )
    
    # 如果客户端不存在或连接已断开，重新连接
    if _vsphere_client is None or not _vsphere_client.is_connected():
        _vsphere_client = VSphereClient(host, username, password, port)
        error = _vsphere_client.connect()
        if error:
            _vsphere_client = None
            return None, error
    
    return _vsphere_client, None
