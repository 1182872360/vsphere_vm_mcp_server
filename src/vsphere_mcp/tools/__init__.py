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
)

from .lifecycle import (
    create_vm_from_template,
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
    # 生命周期工具
    "create_vm_from_template",
]
