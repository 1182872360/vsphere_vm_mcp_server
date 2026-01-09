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
    NetworkInfo,
)
from ..utils.errors import (
    TOOL_DESCRIBE_TEMPLATES,
    TOOL_DESCRIBE_CLUSTERS,
    TOOL_DESCRIBE_FOLDERS,
    TOOL_DESCRIBE_RESOURCE_POOLS,
    TOOL_DESCRIBE_NETWORKS,
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
                disableSslCertValidation=True
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

    def get_networks(self, cluster_name: Optional[str] = None) -> List[NetworkInfo]:
        """获取所有网络"""
        networks = []
        network_objs = self.get_all_objects(vim.Network)
        
        # 添加 DistributedVirtualPortgroup 支持
        dvs_pgs = self.get_all_objects(vim.dvs.DistributedVirtualPortgroup)
        all_networks = list(network_objs) + list(dvs_pgs)
        
        for net in all_networks:
            try:
                # 简单过滤：如果提供了 cluster_name，这里暂时无法直接关联网络和集群
                # vSphere 中网络通常跨集群，或者是数据中心级别的
                # 但可以通过检查网络关联的主机来间接过滤，这里为了性能暂不做深度过滤
                
                network_type = "Standard"
                if isinstance(net, vim.dvs.DistributedVirtualPortgroup):
                    network_type = "Distributed"
                
                networks.append(NetworkInfo(
                    name=net.name,
                    network_id=net._moId,
                    network_type=network_type
                ))
            except Exception as e:
                logger.warning(f"获取网络 {net.name} 信息失败: {e}")
                continue
        
        return networks

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
        network_name: Optional[str] = None,
        cpu: Optional[int] = None,
        memory_mb: Optional[int] = None,
        # Customization Params
        ip_address: Optional[str] = None,
        subnet_mask: Optional[str] = None,
        gateway: Optional[str] = None,
        dns_servers: Optional[List[str]] = None,
        hostname: Optional[str] = None,
        password: Optional[str] = None, # root/admin password
        domain: Optional[str] = None
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
            clone_spec.powerOn = True # Default to power on to apply customization
            clone_spec.template = False
            
            # 配置规格 (ConfigSpec)
            config_spec = vim.vm.ConfigSpec()
            config_changes = False
            device_changes = []

            # 配置 CPU 和内存
            if cpu:
                config_spec.numCPUs = cpu
                config_changes = True
            if memory_mb:
                config_spec.memoryMB = memory_mb
                config_changes = True

            # 配置网络连接 (Device Change)
            if network_name:
                network_spec = self._create_network_spec(template, network_name)
                if network_spec:
                    device_changes.append(network_spec)
                    config_changes = True
                else:
                    return None, MCPError(
                        error_type=ErrorType.RESOURCE_NOT_FOUND,
                        parameter="network_name",
                        message=f"网络 '{network_name}' 不存在或配置失败",
                        suggestion="请使用 describeNetworks 查询可用网络",
                        related_tools=[TOOL_DESCRIBE_NETWORKS]
                    )
            
            if config_changes:
                if device_changes:
                    config_spec.deviceChange = device_changes
                clone_spec.config = config_spec
            
            # 客户机自定义 (Customization Spec)
            if any([ip_address, hostname, password, domain]):
                # Guest OS Detection
                is_windows = "win" in template.config.guestId.lower()
                
                customization_spec = self._create_customization_spec(
                    is_windows=is_windows,
                    hostname=hostname or vm_name,
                    domain=domain,
                    ip_address=ip_address,
                    subnet_mask=subnet_mask,
                    gateway=gateway,
                    dns_servers=dns_servers,
                    password=password
                )
                
                if customization_spec:
                    clone_spec.customization = customization_spec

            # 执行克隆
            task = template.Clone(folder=folder, name=vm_name, spec=clone_spec)
            
            return f"task-{task._moId}", None
            
        except Exception as e:
            return None, parse_vsphere_error(e, "clone_vm")

    def _create_customization_spec(
        self,
        is_windows: bool,
        hostname: str,
        domain: Optional[str] = None,
        ip_address: Optional[str] = None,
        subnet_mask: Optional[str] = None,
        gateway: Optional[str] = None,
        dns_servers: Optional[List[str]] = None,
        password: Optional[str] = None
    ) -> Optional[vim.vm.customization.Specification]:
        """创建 Guest Customization Specification"""
        
        spec = vim.vm.customization.Specification()
        
        # 1. Global IP Settings
        spec.globalIPSettings = vim.vm.customization.GlobalIPSettings()
        if dns_servers:
            spec.globalIPSettings.dnsServerList = dns_servers
        if domain:
            spec.globalIPSettings.dnsSuffixList = [domain]
            
        # 2. Identity (Linux or Windows)
        if is_windows:
            identity = vim.vm.customization.Sysprep()
            
            # UserData
            identity.userData = vim.vm.customization.UserData()
            identity.userData.fullName = "Administrator"
            identity.userData.orgName = "Organization"
            identity.userData.computerName = vim.vm.customization.FixedName()
            identity.userData.computerName.name = hostname
            identity.userData.productId = "" # Windows 许可证密钥

            # GuiUnattended (Password)
            identity.guiUnattended = vim.vm.customization.GuiUnattended()
            if password:
                identity.guiUnattended.password = vim.vm.customization.Password()
                identity.guiUnattended.password.value = password
                identity.guiUnattended.password.plainText = True
            else:
                 # 必须设置，否则 Sysprep 可能失败。
                 identity.guiUnattended.password = None 
            
            identity.guiUnattended.timeZone = 210 # China Standard Time
            identity.guiUnattended.autoLogon = True
            identity.guiUnattended.autoLogonCount = 1
            
            # Identification (Workgroup/Domain)
            identity.identification = vim.vm.customization.Identification()
            if domain:
                identity.identification.joinDomain = domain
                identity.identification.domainAdmin = "Administrator" # 简化：假设域管理员
                if password:
                    identity.identification.domainAdminPassword = vim.vm.customization.Password()
                    identity.identification.domainAdminPassword.value = password
                    identity.identification.domainAdminPassword.plainText = True
            else:
                identity.identification.joinWorkgroup = "WORKGROUP"
            
            spec.identity = identity
            
        else: # Linux
            identity = vim.vm.customization.LinuxPrep()
            identity.domain = domain or "localdomain"
            identity.hostName = vim.vm.customization.FixedName()
            identity.hostName.name = hostname
            identity.hwClockUTC = True
            identity.timeZone = "Asia/Shanghai"
            
            spec.identity = identity
            # Linux root password setting via LinuxPrep is limited/not supported in the same way.
            # Warning: password argument will be ignored for Linux in standard customization.
            
        # 3. NIC Setting (IP)
        adapter_mapping = vim.vm.customization.AdapterMapping()
        adapter_mapping.adapter = vim.vm.customization.IPSettings()
        
        if ip_address:
            adapter_mapping.adapter.ip = vim.vm.customization.FixedIp()
            adapter_mapping.adapter.ip.ipAddress = ip_address
            adapter_mapping.adapter.subnetMask = subnet_mask or "255.255.255.0"
            if gateway:
                adapter_mapping.adapter.gateway = [gateway]
        else:
            adapter_mapping.adapter.ip = vim.vm.customization.DhcpIp()
            
        spec.nicSettingMap = [adapter_mapping]
        
        return spec

    def get_vm_power_state(self, vm_name: str) -> Tuple[Optional[str], Optional[MCPError]]:
        """获取虚拟机的电源状态"""
        if not self.is_connected():
            return None, MCPError(ErrorType.CONNECTION_ERROR, "Not connected to vSphere")

        try:
            vm = self.find_object_by_name(vm_name, vim.VirtualMachine)
            if not vm:
                return None, MCPError(ErrorType.RESOURCE_NOT_FOUND, f"Virtual machine '{vm_name}' not found")
            
            return str(vm.runtime.powerState), None
        except Exception as e:
            logger.error(f"Error getting power state for VM '{vm_name}': {e}")
            return None, parse_vsphere_error(e, "get_vm_power_state")

    def reconfigure_vm(
        self,
        vm_name: str,
        cpu: Optional[int] = None,
        memory_mb: Optional[int] = None,
        disk_size_gb: Optional[int] = None,
        network_name: Optional[str] = None
    ) -> Tuple[Optional[str], Optional[MCPError]]:
        """
        重新配置虚拟机 (修改 CPU/内存/磁盘/网络)
        注意：虚拟机必须处于关机状态
        
        Args:
            vm_name: 虚拟机名称
            cpu: 新的 CPU 核数
            memory_mb: 新的内存大小 (MB)
            disk_size_gb: 新的磁盘大小 (GB)，仅允许扩容
            network_name: 新的网络名称 (修改第一块网卡)
            
        Returns:
            Tuple[task_id, error_message]
        """
        if not self.is_connected():
            return None, MCPError(ErrorType.CONNECTION_ERROR, "Not connected to vSphere")

        try:
            # 1. 查找虚拟机
            vm = self.find_object_by_name(vm_name, vim.VirtualMachine)
            if not vm:
                return None, MCPError(ErrorType.RESOURCE_NOT_FOUND, f"Virtual machine '{vm_name}' not found")

            # 2. 检查电源状态 (必须关机)
            if vm.runtime.powerState != vim.VirtualMachine.PowerState.poweredOff:
                return None, MCPError(
                    ErrorType.INVALID_OPERATION, 
                    f"VM '{vm_name}' is currently {vm.runtime.powerState}. It must be powered off to reconfigure.",
                    suggestion="Please power off the VM first. You can use 'getVMPowerState' to check the status."
                )

            # 3. 创建配置规格
            config_spec = vim.vm.ConfigSpec()
            changed = False
            device_changes = []

            # CPU & Memory
            if cpu is not None:
                if cpu <= 0:
                    return None, MCPError(ErrorType.INVALID_PARAMETER, "CPU count must be positive")
                config_spec.numCPUs = cpu
                changed = True
            
            if memory_mb is not None:
                if memory_mb <= 0:
                    return None, MCPError(ErrorType.INVALID_PARAMETER, "Memory size must be positive")
                config_spec.memoryMB = int(memory_mb)
                changed = True

            # Disk Expansion
            if disk_size_gb is not None:
                if disk_size_gb <= 0:
                    return None, MCPError(ErrorType.INVALID_PARAMETER, "Disk size must be positive")
                
                # 找到第一个磁盘
                disk = None
                for device in vm.config.hardware.device:
                    if isinstance(device, vim.vm.device.VirtualDisk):
                        disk = device
                        break
                
                if not disk:
                     return None, MCPError(ErrorType.RESOURCE_NOT_FOUND, "No virtual disk found on VM to expand")
                
                current_size_gb = disk.capacityInKB / (1024 * 1024)
                if disk_size_gb < current_size_gb:
                    return None, MCPError(
                        ErrorType.INVALID_PARAMETER, 
                        f"Cannot shrink disk (Current: {current_size_gb} GB, Requested: {disk_size_gb} GB). Only expansion is supported."
                    )
                elif disk_size_gb > current_size_gb:
                    disk_spec = vim.vm.device.VirtualDeviceSpec()
                    disk_spec.operation = vim.vm.device.VirtualDeviceSpec.Operation.edit
                    disk_spec.device = disk
                    disk_spec.device.capacityInKB = int(disk_size_gb * 1024 * 1024)
                    device_changes.append(disk_spec)
                    changed = True

            # Network Change
            if network_name:
                # 找到第一块网卡
                nic = None
                for device in vm.config.hardware.device:
                    if isinstance(device, vim.vm.device.VirtualEthernetCard):
                        nic = device
                        break
                
                if not nic:
                    return None, MCPError(ErrorType.RESOURCE_NOT_FOUND, "No network adapter found on VM to reconfigure")

                # 复用 _create_network_spec 的逻辑来查找网络并构建 BackingInfo
                # 注意：这里我们临时传入 vm 作为 template 参数，因为 _create_network_spec 只需要 helper 功能
                # 或者我们可以重构 _create_network_spec，但为了简单，我们直接在这里实现查找网络的逻辑
                
                # 查找网络
                target_network = None
                content = self.get_content()
                
                # 尝试标准网络
                container = content.viewManager.CreateContainerView(content.rootFolder, [vim.Network], True)
                for net in container.view:
                    if net.name == network_name:
                        target_network = net
                        break
                container.Destroy()
                
                # 尝试分布式端口组
                if not target_network:
                    container = content.viewManager.CreateContainerView(content.rootFolder, [vim.dvs.DistributedVirtualPortgroup], True)
                    for pg in container.view:
                        if pg.name == network_name:
                            target_network = pg
                            break
                    container.Destroy()

                if not target_network:
                    return None, MCPError(
                        ErrorType.RESOURCE_NOT_FOUND, 
                        f"Network '{network_name}' not found"
                    )

                nic_spec = vim.vm.device.VirtualDeviceSpec()
                nic_spec.operation = vim.vm.device.VirtualDeviceSpec.Operation.edit
                nic_spec.device = nic
                
                # 设置 Backing
                if isinstance(target_network, vim.dvs.DistributedVirtualPortgroup):
                    dvs_port_connection = vim.dvs.PortConnection()
                    dvs_port_connection.portgroupKey = target_network.key
                    dvs_port_connection.switchUuid = target_network.config.distributedVirtualSwitch.uuid
                    nic.backing = vim.vm.device.VirtualEthernetCard.DistributedVirtualPortBackingInfo()
                    nic.backing.port = dvs_port_connection
                else:
                    nic.backing = vim.vm.device.VirtualEthernetCard.NetworkBackingInfo()
                    nic.backing.network = target_network
                    nic.backing.deviceName = network_name
                
                device_changes.append(nic_spec)
                changed = True

            if not changed:
                return None, MCPError(ErrorType.MISSING_PARAMETER, "No configuration changes specified")

            if device_changes:
                config_spec.deviceChange = device_changes

            # 3. 创建重新配置任务
            task = vm.ReconfigVM_Task(spec=config_spec)
            
            # 返回任务 ID (格式: task-123)
            return f"task-{task._moId}", None

        except Exception as e:
            logger.error(f"Error reconfiguring VM '{vm_name}': {e}")
            return None, parse_vsphere_error(e, "reconfigure_vm")

    # =========================================================================
    # 辅助方法
    # =========================================================================

    def _create_network_spec(self, template, network_name: str) -> Optional[vim.vm.device.VirtualDeviceSpec]:
        """创建网络配置规格"""
        # 1. 查找目标网络对象
        content = self.get_content()
        network = None
        # 尝试查找标准网络
        container = content.viewManager.CreateContainerView(content.rootFolder, [vim.Network], True)
        for net in container.view:
            if net.name == network_name:
                network = net
                break
        container.Destroy()
        
        # 如果不是标准网络，尝试查找分布式端口组
        if not network:
            container = content.viewManager.CreateContainerView(content.rootFolder, [vim.dvs.DistributedVirtualPortgroup], True)
            for pg in container.view:
                if pg.name == network_name:
                    network = pg
                    break
            container.Destroy()
            
        if not network:
            return None

        # 2. 找到模板中的第一个网卡
        nic = None
        for device in template.config.hardware.device:
            if isinstance(device, vim.vm.device.VirtualEthernetCard):
                nic = device
                break
        
        if not nic:
            return None # 模板没有网卡，无法修改

        # 3. 创建设备修改规格
        nic_spec = vim.vm.device.VirtualDeviceSpec()
        nic_spec.operation = vim.vm.device.VirtualDeviceSpec.Operation.edit
        nic_spec.device = nic
        
        # 4. 配置 BackingInfo
        if isinstance(network, vim.dvs.DistributedVirtualPortgroup):
            # 分布式交换机
            dvs_port_connection = vim.dvs.PortConnection()
            dvs_port_connection.portgroupKey = network.key
            dvs_port_connection.switchUuid = network.config.distributedVirtualSwitch.uuid
            
            nic.backing = vim.vm.device.VirtualEthernetCard.DistributedVirtualPortBackingInfo()
            nic.backing.port = dvs_port_connection
        else:
            # 标准交换机
            nic.backing = vim.vm.device.VirtualEthernetCard.NetworkBackingInfo()
            nic.backing.network = network
            nic.backing.deviceName = network_name
        
        # 连接状态
        nic.connectable = vim.vm.device.VirtualDevice.ConnectInfo()
        nic.connectable.startConnected = True
        nic.connectable.allowGuestControl = True
        nic.connectable.connected = True
        
        return nic_spec

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
