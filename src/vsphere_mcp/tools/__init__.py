# -*- coding: utf-8 -*-
"""
vSphere MCP Server - 工具包导出
"""

from .query import (
    describe_templates,
    describe_hosts,
    describe_clusters,
    describe_folders,
    describe_resource_pools,
    describe_networks,
    describe_vms,
    get_vm_power_state,
)

from .lifecycle import (
    create_vm_from_template,
    reconfigure_vm,
)

__all__ = [
    # 查询工具
    "describe_templates",
    "describe_hosts",
    "describe_clusters",
    "describe_folders",
    "describe_resource_pools",
    "describe_networks",
    "describe_vms",
    "get_vm_power_state",
    # 生命周期工具
    "create_vm_from_template",
    "reconfigure_vm",
]
