# -*- coding: utf-8 -*-
"""
vSphere MCP Server - 客户端包导出
"""

from .vsphere import (
    VSphereClient,
    get_vsphere_client,
    PYVMOMI_AVAILABLE,
)

__all__ = [
    "VSphereClient",
    "get_vsphere_client",
    "PYVMOMI_AVAILABLE",
]
