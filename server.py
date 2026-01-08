# -*- coding: utf-8 -*-
import os
import re
import logging
from enum import Enum
from contextlib import asynccontextmanager
from collections.abc import AsyncGenerator
from typing import Dict, Any, Optional, List, Union

from pydantic import Field, BaseModel, ConfigDict

from mcp.server.fastmcp import FastMCP

from alibabacloud_ecs20140526.client import Client as Ecs20140526Client
from alibabacloud_tea_openapi import models as open_api_models
from alibabacloud_ecs20140526 import models as ecs_20140526_models
from alibabacloud_tea_util import models as util_models

# --- Global Logger ---
logger = logging.getLogger(__name__)


# =============================================================================
# MCP 最佳实践：结构化错误类型定义
# =============================================================================
class ErrorType(str, Enum):
    """错误类型枚举，帮助 LLM 理解错误性质"""
    MISSING_PARAMETER = "MISSING_PARAMETER"          # 必需参数缺失
    INVALID_PARAMETER = "INVALID_PARAMETER"          # 参数格式或值无效
    RESOURCE_NOT_FOUND = "RESOURCE_NOT_FOUND"        # 资源不存在
    PERMISSION_DENIED = "PERMISSION_DENIED"          # 权限不足
    QUOTA_EXCEEDED = "QUOTA_EXCEEDED"                # 配额超限
    DEPENDENCY_MISSING = "DEPENDENCY_MISSING"        # 依赖资源缺失
    API_ERROR = "API_ERROR"                          # API 调用错误
    PRECONDITION_FAILED = "PRECONDITION_FAILED"      # 前置条件不满足


# =============================================================================
# MCP 最佳实践：结构化响应模型
# =============================================================================
class MyBaseModel(BaseModel):
    model_config = ConfigDict(json_dumps_params={'ensure_ascii': False})


class ToolSuggestion(MyBaseModel):
    """工具建议模型 - 引导 LLM 调用正确的工具"""
    tool_name: str = Field(description="建议调用的工具名称")
    description: str = Field(description="调用该工具的原因说明")
    example_params: Optional[Dict[str, Any]] = Field(default=None, description="示例参数")


class MCPError(MyBaseModel):
    """
    MCP 最佳实践：结构化错误响应
    
    这个模型确保错误信息对 LLM 友好，包含：
    1. 错误类型 - 便于 LLM 分类处理
    2. 人类可读消息 - 便于理解问题
    3. 解决方案建议 - 告诉 LLM 如何修复
    4. 相关工具 - 引导 LLM 调用正确的工具
    """
    error_type: ErrorType = Field(description="错误类型")
    message: str = Field(description="人类可读的错误描述")
    parameter: Optional[str] = Field(default=None, description="出错的参数名")
    suggestion: str = Field(description="给 LLM 的解决方案建议")
    related_tools: Optional[List[ToolSuggestion]] = Field(
        default=None, 
        description="相关工具推荐，LLM 可以调用这些工具来解决问题"
    )
    
    def __str__(self) -> str:
        """格式化输出，便于 LLM 解析"""
        parts = [
            f"[{self.error_type.value}] {self.message}",
            f"建议: {self.suggestion}"
        ]
        if self.related_tools:
            tools_info = ", ".join([f"{t.tool_name}({t.description})" for t in self.related_tools])
            parts.append(f"相关工具: {tools_info}")
        return "\n".join(parts)


class MCPResult(MyBaseModel):
    """
    MCP 最佳实践：统一响应模型
    
    所有工具响应都使用这个模型，确保结构一致性
    """
    success: bool = Field(description="操作是否成功")
    data: Optional[Any] = Field(default=None, description="成功时的数据")
    error: Optional[MCPError] = Field(default=None, description="失败时的错误信息")
    request_id: Optional[str] = Field(default=None, description="请求 ID，用于追踪")


# =============================================================================
# 业务数据模型
# =============================================================================
class InstanceInfo(MyBaseModel):
    InstanceId: Optional[str] = Field(description="ECS 实例 ID", default=None)
    InstanceName: Optional[str] = Field(description="实例名称", default=None)
    InstanceType: Optional[str] = Field(description="实例规格", default=None)
    Status: Optional[str] = Field(description="实例状态", default=None)
    RegionId: Optional[str] = Field(description="地域 ID", default=None)
    ZoneId: Optional[str] = Field(description="可用区 ID", default=None)
    PublicIpAddress: Optional[List[str]] = Field(description="公网 IP 地址列表", default=None)
    InnerIpAddress: Optional[List[str]] = Field(description="私网 IP 地址列表", default=None)
    HostName: Optional[str] = Field(description="主机名", default=None)
    ImageId: Optional[str] = Field(description="镜像 ID", default=None)
    CreationTime: Optional[str] = Field(description="创建时间", default=None)


class InstanceDetail(MyBaseModel):
    InstanceId: Optional[str] = Field(description="ECS 实例 ID", default=None)
    InstanceName: Optional[str] = Field(description="实例名称", default=None)
    InstanceType: Optional[str] = Field(description="实例规格", default=None)
    Status: Optional[str] = Field(description="实例状态", default=None)
    RegionId: Optional[str] = Field(description="地域 ID", default=None)
    ZoneId: Optional[str] = Field(description="可用区 ID", default=None)
    Cpu: Optional[int] = Field(description="CPU 核数", default=None)
    Memory: Optional[int] = Field(description="内存大小 (MB)", default=None)
    OSName: Optional[str] = Field(description="操作系统名称", default=None)
    OSType: Optional[str] = Field(description="操作系统类型", default=None)
    PublicIpAddress: Optional[List[str]] = Field(description="公网 IP 地址列表", default=None)
    InnerIpAddress: Optional[List[str]] = Field(description="私网 IP 地址列表", default=None)
    VpcId: Optional[str] = Field(description="VPC ID", default=None)
    VSwitchId: Optional[str] = Field(description="交换机 ID", default=None)
    SecurityGroupIds: Optional[List[str]] = Field(description="安全组 ID 列表", default=None)
    HostName: Optional[str] = Field(description="主机名", default=None)
    ImageId: Optional[str] = Field(description="镜像 ID", default=None)
    CreationTime: Optional[str] = Field(description="创建时间", default=None)
    ExpiredTime: Optional[str] = Field(description="过期时间", default=None)
    InstanceChargeType: Optional[str] = Field(description="计费类型", default=None)


class InstanceTypeInfo(MyBaseModel):
    """实例规格信息"""
    InstanceTypeId: Optional[str] = Field(description="实例规格 ID", default=None)
    InstanceTypeFamily: Optional[str] = Field(description="实例规格族", default=None)
    CpuCoreCount: Optional[int] = Field(description="CPU 核数", default=None)
    MemorySize: Optional[float] = Field(description="内存大小 (GB)", default=None)
    LocalStorageCategory: Optional[str] = Field(description="本地存储类型", default=None)


class ImageInfo(MyBaseModel):
    """镜像信息"""
    ImageId: Optional[str] = Field(description="镜像 ID", default=None)
    ImageName: Optional[str] = Field(description="镜像名称", default=None)
    OSName: Optional[str] = Field(description="操作系统名称", default=None)
    OSType: Optional[str] = Field(description="操作系统类型", default=None)
    Platform: Optional[str] = Field(description="平台", default=None)
    Size: Optional[int] = Field(description="镜像大小 (GB)", default=None)


class SecurityGroupInfo(MyBaseModel):
    """安全组信息"""
    SecurityGroupId: Optional[str] = Field(description="安全组 ID", default=None)
    SecurityGroupName: Optional[str] = Field(description="安全组名称", default=None)
    Description: Optional[str] = Field(description="描述", default=None)
    VpcId: Optional[str] = Field(description="VPC ID", default=None)


class VSwitchInfo(MyBaseModel):
    """交换机信息"""
    VSwitchId: Optional[str] = Field(description="交换机 ID", default=None)
    VSwitchName: Optional[str] = Field(description="交换机名称", default=None)
    ZoneId: Optional[str] = Field(description="可用区 ID", default=None)
    VpcId: Optional[str] = Field(description="VPC ID", default=None)
    CidrBlock: Optional[str] = Field(description="网段", default=None)
    AvailableIpAddressCount: Optional[int] = Field(description="可用 IP 数量", default=None)


class RegionInfo(MyBaseModel):
    RegionId: Optional[str] = Field(description="地域 ID", default=None)
    LocalName: Optional[str] = Field(description="地域名称", default=None)
    RegionEndpoint: Optional[str] = Field(description="地域接入点", default=None)


class ZoneInfo(MyBaseModel):
    ZoneId: Optional[str] = Field(description="可用区 ID", default=None)
    LocalName: Optional[str] = Field(description="可用区名称", default=None)


# =============================================================================
# 工具建议常量 - 用于错误响应中引导 LLM
# =============================================================================
TOOL_DESCRIBE_INSTANCE_TYPES = ToolSuggestion(
    tool_name="describeInstanceTypes",
    description="查询可用的实例规格列表",
    example_params={"region_id": "cn-hangzhou"}
)

TOOL_DESCRIBE_IMAGES = ToolSuggestion(
    tool_name="describeImages",
    description="查询可用的镜像列表",
    example_params={"region_id": "cn-hangzhou", "image_owner_alias": "system"}
)

TOOL_DESCRIBE_SECURITY_GROUPS = ToolSuggestion(
    tool_name="describeSecurityGroups",
    description="查询可用的安全组列表",
    example_params={"region_id": "cn-hangzhou"}
)

TOOL_DESCRIBE_VSWITCHES = ToolSuggestion(
    tool_name="describeVSwitches",
    description="查询可用的交换机列表",
    example_params={"region_id": "cn-hangzhou"}
)

TOOL_DESCRIBE_REGIONS = ToolSuggestion(
    tool_name="describeRegions",
    description="查询可用的地域列表",
    example_params={}
)

TOOL_DESCRIBE_ZONES = ToolSuggestion(
    tool_name="describeZones",
    description="查询指定地域的可用区列表",
    example_params={"region_id": "cn-hangzhou"}
)


# =============================================================================
# 参数验证辅助函数
# =============================================================================
def validate_region_id(region_id: Optional[str]) -> Optional[MCPError]:
    """验证地域 ID 格式"""
    if not region_id:
        return MCPError(
            error_type=ErrorType.MISSING_PARAMETER,
            parameter="region_id",
            message="缺少必需参数: region_id (地域 ID)",
            suggestion="请提供有效的地域 ID，如 'cn-hangzhou', 'cn-shanghai' 等",
            related_tools=[TOOL_DESCRIBE_REGIONS]
        )
    # 简单的格式验证
    if not re.match(r'^[a-z]{2,3}-[a-z]+-?\d*$', region_id):
        return MCPError(
            error_type=ErrorType.INVALID_PARAMETER,
            parameter="region_id",
            message=f"无效的地域 ID 格式: '{region_id}'",
            suggestion="地域 ID 格式应为 'cn-hangzhou', 'ap-southeast-1' 等",
            related_tools=[TOOL_DESCRIBE_REGIONS]
        )
    return None


def validate_instance_type(instance_type: Optional[str], region_id: str) -> Optional[MCPError]:
    """验证实例规格"""
    if not instance_type:
        return MCPError(
            error_type=ErrorType.MISSING_PARAMETER,
            parameter="instance_type",
            message="缺少必需参数: instance_type (实例规格)",
            suggestion=f"请先使用 describeInstanceTypes 工具查询 {region_id} 地域可用的实例规格",
            related_tools=[ToolSuggestion(
                tool_name="describeInstanceTypes",
                description="查询可用的实例规格",
                example_params={"region_id": region_id}
            )]
        )
    # 简单的格式验证
    if not re.match(r'^ecs\.[a-z0-9-]+\.[a-z0-9]+$', instance_type):
        return MCPError(
            error_type=ErrorType.INVALID_PARAMETER,
            parameter="instance_type",
            message=f"无效的实例规格格式: '{instance_type}'",
            suggestion="实例规格格式应为 'ecs.g7.large', 'ecs.c7.xlarge' 等",
            related_tools=[ToolSuggestion(
                tool_name="describeInstanceTypes",
                description="查询可用的实例规格",
                example_params={"region_id": region_id}
            )]
        )
    return None


def validate_image_id(image_id: Optional[str], region_id: str) -> Optional[MCPError]:
    """验证镜像 ID"""
    if not image_id:
        return MCPError(
            error_type=ErrorType.MISSING_PARAMETER,
            parameter="image_id",
            message="缺少必需参数: image_id (镜像 ID)",
            suggestion=f"请先使用 describeImages 工具查询 {region_id} 地域可用的镜像",
            related_tools=[ToolSuggestion(
                tool_name="describeImages",
                description="查询可用的镜像",
                example_params={"region_id": region_id, "image_owner_alias": "system"}
            )]
        )
    return None


def validate_security_group_id(security_group_id: Optional[str], region_id: str) -> Optional[MCPError]:
    """验证安全组 ID"""
    if not security_group_id:
        return MCPError(
            error_type=ErrorType.MISSING_PARAMETER,
            parameter="security_group_id",
            message="缺少必需参数: security_group_id (安全组 ID)",
            suggestion=f"请先使用 describeSecurityGroups 工具查询 {region_id} 地域可用的安全组",
            related_tools=[ToolSuggestion(
                tool_name="describeSecurityGroups",
                description="查询可用的安全组",
                example_params={"region_id": region_id}
            )]
        )
    if not security_group_id.startswith("sg-"):
        return MCPError(
            error_type=ErrorType.INVALID_PARAMETER,
            parameter="security_group_id",
            message=f"无效的安全组 ID 格式: '{security_group_id}'",
            suggestion="安全组 ID 应以 'sg-' 开头",
            related_tools=[ToolSuggestion(
                tool_name="describeSecurityGroups",
                description="查询可用的安全组",
                example_params={"region_id": region_id}
            )]
        )
    return None


def validate_vswitch_id(v_switch_id: Optional[str], region_id: str) -> Optional[MCPError]:
    """验证交换机 ID (VPC 网络下必填)"""
    if v_switch_id and not v_switch_id.startswith("vsw-"):
        return MCPError(
            error_type=ErrorType.INVALID_PARAMETER,
            parameter="v_switch_id",
            message=f"无效的交换机 ID 格式: '{v_switch_id}'",
            suggestion="交换机 ID 应以 'vsw-' 开头",
            related_tools=[ToolSuggestion(
                tool_name="describeVSwitches",
                description="查询可用的交换机",
                example_params={"region_id": region_id}
            )]
        )
    return None


def parse_api_error(error: Exception, region_id: str) -> MCPError:
    """
    解析阿里云 API 错误，转换为结构化的 MCPError
    
    这是 MCP 最佳实践的核心：将底层 API 错误转换为对 LLM 友好的错误信息
    """
    error_msg = str(error)
    error_code = getattr(error, 'code', '') or ''
    
    # 实例规格不存在
    if 'InvalidInstanceType.NotFound' in error_code or 'InvalidInstanceType' in error_msg:
        return MCPError(
            error_type=ErrorType.RESOURCE_NOT_FOUND,
            parameter="instance_type",
            message=f"指定的实例规格在当前地域不可用",
            suggestion=f"请使用 describeInstanceTypes 工具查询 {region_id} 地域支持的实例规格",
            related_tools=[ToolSuggestion(
                tool_name="describeInstanceTypes",
                description="查询可用的实例规格",
                example_params={"region_id": region_id}
            )]
        )
    
    # 镜像不存在
    if 'InvalidImageId.NotFound' in error_code or 'InvalidImageId' in error_msg:
        return MCPError(
            error_type=ErrorType.RESOURCE_NOT_FOUND,
            parameter="image_id",
            message="指定的镜像不存在或无权限访问",
            suggestion=f"请使用 describeImages 工具查询 {region_id} 地域可用的镜像",
            related_tools=[ToolSuggestion(
                tool_name="describeImages",
                description="查询可用的镜像",
                example_params={"region_id": region_id, "image_owner_alias": "system"}
            )]
        )
    
    # 安全组不存在
    if 'InvalidSecurityGroupId.NotFound' in error_code or 'InvalidSecurityGroupId' in error_msg:
        return MCPError(
            error_type=ErrorType.RESOURCE_NOT_FOUND,
            parameter="security_group_id",
            message="指定的安全组不存在",
            suggestion=f"请使用 describeSecurityGroups 工具查询 {region_id} 地域可用的安全组",
            related_tools=[ToolSuggestion(
                tool_name="describeSecurityGroups",
                description="查询可用的安全组",
                example_params={"region_id": region_id}
            )]
        )
    
    # 交换机不存在
    if 'InvalidVSwitchId.NotFound' in error_code or 'InvalidVSwitchId' in error_msg:
        return MCPError(
            error_type=ErrorType.RESOURCE_NOT_FOUND,
            parameter="v_switch_id",
            message="指定的交换机不存在",
            suggestion=f"请使用 describeVSwitches 工具查询 {region_id} 地域可用的交换机",
            related_tools=[ToolSuggestion(
                tool_name="describeVSwitches",
                description="查询可用的交换机",
                example_params={"region_id": region_id}
            )]
        )
    
    # 配额超限
    if 'QuotaExceeded' in error_code or 'quota' in error_msg.lower():
        return MCPError(
            error_type=ErrorType.QUOTA_EXCEEDED,
            message="资源配额不足",
            suggestion="请联系管理员提升配额，或减少创建的实例数量"
        )
    
    # 权限不足
    if 'Forbidden' in error_code or 'permission' in error_msg.lower():
        return MCPError(
            error_type=ErrorType.PERMISSION_DENIED,
            message="权限不足，无法执行此操作",
            suggestion="请检查当前账号是否有足够的 ECS 操作权限"
        )
    
    # VPC 网络需要交换机
    if 'VSwitch' in error_msg and 'required' in error_msg.lower():
        return MCPError(
            error_type=ErrorType.DEPENDENCY_MISSING,
            parameter="v_switch_id",
            message="VPC 网络下创建实例需要指定交换机",
            suggestion=f"请使用 describeVSwitches 工具查询 {region_id} 地域可用的交换机，并在请求中指定 v_switch_id 参数",
            related_tools=[ToolSuggestion(
                tool_name="describeVSwitches",
                description="查询可用的交换机",
                example_params={"region_id": region_id}
            )]
        )
    
    # 默认错误处理
    return MCPError(
        error_type=ErrorType.API_ERROR,
        message=f"API 调用失败: {error_msg}",
        suggestion="请检查参数是否正确，或稍后重试"
    )


# =============================================================================
# Aliyun Client Creation
# =============================================================================
def create_client(region_id: str = "cn-hangzhou") -> Ecs20140526Client:
    """创建 ECS 客户端"""
    config = open_api_models.Config(
        access_key_id=os.getenv('ALIBABA_CLOUD_ACCESS_KEY_ID'),
        access_key_secret=os.getenv('ALIBABA_CLOUD_ACCESS_KEY_SECRET'),
        security_token=os.getenv('ALIBABA_CLOUD_SECURITY_TOKEN'),
        read_timeout=60 * 1000
    )
    config.endpoint = f'ecs.{region_id}.aliyuncs.com'
    config.user_agent = "ecs-mcp"
    return Ecs20140526Client(config)


# =============================================================================
# Core API Functions - 带智能错误处理
# =============================================================================
async def describe_instances(
        region_id: str = Field(description="地域 ID，如 cn-hangzhou。如不确定可用地域，请先调用 describeRegions"),
        instance_ids: Optional[List[str]] = Field(default=None, description="实例 ID 列表"),
        instance_name: Optional[str] = Field(default=None, description="实例名称，支持模糊匹配"),
        status: Optional[str] = Field(default=None, description="实例状态: Running, Stopped, Starting, Stopping"),
        page_number: int = Field(default=1, description="页码"),
        page_size: int = Field(default=10, description="每页数量，最大 100")
) -> MCPResult:
    """查询 ECS 实例列表"""
    # 参数验证
    if error := validate_region_id(region_id):
        return MCPResult(success=False, error=error)
    
    client = create_client(region_id)
    req = ecs_20140526_models.DescribeInstancesRequest(
        region_id=region_id,
        page_number=page_number,
        page_size=page_size
    )
    if instance_ids:
        req.instance_ids = str(instance_ids)
    if instance_name:
        req.instance_name = instance_name
    if status:
        req.status = status

    runtime = util_models.RuntimeOptions()
    try:
        resp = client.describe_instances_with_options(req, runtime)
        if resp and resp.body and resp.body.instances:
            instances = resp.body.instances.instance or []
            result = []
            for inst in instances:
                result.append(InstanceInfo(
                    InstanceId=inst.instance_id,
                    InstanceName=inst.instance_name,
                    InstanceType=inst.instance_type,
                    Status=inst.status,
                    RegionId=inst.region_id,
                    ZoneId=inst.zone_id,
                    PublicIpAddress=inst.public_ip_address.ip_address if inst.public_ip_address else None,
                    InnerIpAddress=inst.inner_ip_address.ip_address if inst.inner_ip_address else None,
                    HostName=inst.host_name,
                    ImageId=inst.image_id,
                    CreationTime=inst.creation_time
                ))
            return MCPResult(success=True, data=result, request_id=resp.body.request_id)
        return MCPResult(success=True, data=[], request_id=resp.body.request_id if resp.body else None)
    except Exception as e:
        logger.error(f"Error in describe_instances: {e}")
        return MCPResult(success=False, error=parse_api_error(e, region_id))


async def describe_instance_attribute(
        region_id: str = Field(description="地域 ID"),
        instance_id: str = Field(description="实例 ID，可通过 describeInstances 获取")
) -> MCPResult:
    """获取 ECS 实例详细信息"""
    if error := validate_region_id(region_id):
        return MCPResult(success=False, error=error)
    
    if not instance_id:
        return MCPResult(success=False, error=MCPError(
            error_type=ErrorType.MISSING_PARAMETER,
            parameter="instance_id",
            message="缺少必需参数: instance_id",
            suggestion="请先使用 describeInstances 工具查询实例列表获取实例 ID",
            related_tools=[ToolSuggestion(
                tool_name="describeInstances",
                description="查询实例列表",
                example_params={"region_id": region_id}
            )]
        ))
    
    client = create_client(region_id)
    req = ecs_20140526_models.DescribeInstanceAttributeRequest(instance_id=instance_id)
    runtime = util_models.RuntimeOptions()
    try:
        resp = client.describe_instance_attribute_with_options(req, runtime)
        if resp and resp.body:
            inst = resp.body
            return MCPResult(success=True, data=InstanceDetail(
                InstanceId=inst.instance_id,
                InstanceName=inst.instance_name,
                InstanceType=inst.instance_type,
                Status=inst.status,
                RegionId=inst.region_id,
                ZoneId=inst.zone_id,
                Cpu=inst.cpu,
                Memory=inst.memory,
                PublicIpAddress=inst.public_ip_address.ip_address if inst.public_ip_address else None,
                InnerIpAddress=inst.inner_ip_address.ip_address if inst.inner_ip_address else None,
                VpcId=inst.vpc_attributes.vpc_id if inst.vpc_attributes else None,
                VSwitchId=inst.vpc_attributes.v_switch_id if inst.vpc_attributes else None,
                SecurityGroupIds=inst.security_group_ids.security_group_id if inst.security_group_ids else None,
                HostName=inst.host_name,
                ImageId=inst.image_id,
                CreationTime=inst.creation_time,
                ExpiredTime=inst.expired_time,
                InstanceChargeType=inst.instance_charge_type
            ), request_id=resp.body.request_id if hasattr(resp.body, 'request_id') else None)
        return MCPResult(success=False, error=MCPError(
            error_type=ErrorType.RESOURCE_NOT_FOUND,
            message=f"实例 {instance_id} 不存在",
            suggestion="请检查实例 ID 是否正确"
        ))
    except Exception as e:
        logger.error(f"Error in describe_instance_attribute: {e}")
        return MCPResult(success=False, error=parse_api_error(e, region_id))


async def run_instances(
        region_id: str = Field(description="地域 ID，如不确定请先调用 describeRegions"),
        image_id: str = Field(description="镜像 ID，如不确定请先调用 describeImages 查询可用镜像"),
        instance_type: str = Field(description="实例规格，如 ecs.g7.large。如不确定请先调用 describeInstanceTypes"),
        security_group_id: str = Field(description="安全组 ID，如不确定请先调用 describeSecurityGroups"),
        v_switch_id: Optional[str] = Field(default=None, description="交换机 ID，VPC 网络必填。可通过 describeVSwitches 查询"),
        zone_id: Optional[str] = Field(default=None, description="可用区 ID，如不确定请先调用 describeZones"),
        instance_name: Optional[str] = Field(default=None, description="实例名称"),
        host_name: Optional[str] = Field(default=None, description="主机名"),
        password: Optional[str] = Field(default=None, description="实例登录密码，8-30 位，需包含大小写字母和数字"),
        amount: int = Field(default=1, description="创建实例数量，1-100"),
        system_disk_size: int = Field(default=40, description="系统盘大小 (GB)，最小 20"),
        system_disk_category: str = Field(default="cloud_essd", description="系统盘类型: cloud_essd, cloud_ssd, cloud_efficiency"),
        instance_charge_type: str = Field(default="PostPaid", description="计费类型: PostPaid(按量付费) 或 PrePaid(包年包月)"),
        internet_max_bandwidth_out: int = Field(default=0, description="公网出带宽 (Mbps)，0 表示不分配公网 IP")
) -> MCPResult:
    """
    创建 ECS 实例
    
    注意：创建实例前，请确保已准备好以下资源：
    1. 地域 (region_id) - 可通过 describeRegions 查询
    2. 镜像 (image_id) - 可通过 describeImages 查询
    3. 实例规格 (instance_type) - 可通过 describeInstanceTypes 查询
    4. 安全组 (security_group_id) - 可通过 describeSecurityGroups 查询
    5. 交换机 (v_switch_id) - VPC 网络必填，可通过 describeVSwitches 查询
    """
    # 参数验证链
    if error := validate_region_id(region_id):
        return MCPResult(success=False, error=error)
    
    if error := validate_instance_type(instance_type, region_id):
        return MCPResult(success=False, error=error)
    
    if error := validate_image_id(image_id, region_id):
        return MCPResult(success=False, error=error)
    
    if error := validate_security_group_id(security_group_id, region_id):
        return MCPResult(success=False, error=error)
    
    if error := validate_vswitch_id(v_switch_id, region_id):
        return MCPResult(success=False, error=error)
    
    # 密码格式验证
    if password:
        if len(password) < 8 or len(password) > 30:
            return MCPResult(success=False, error=MCPError(
                error_type=ErrorType.INVALID_PARAMETER,
                parameter="password",
                message="密码长度必须在 8-30 位之间",
                suggestion="请设置 8-30 位的密码，需包含大小写字母和数字"
            ))
    
    client = create_client(region_id)

    system_disk = ecs_20140526_models.RunInstancesRequestSystemDisk(
        size=str(system_disk_size),
        category=system_disk_category
    )

    req = ecs_20140526_models.RunInstancesRequest(
        region_id=region_id,
        image_id=image_id,
        instance_type=instance_type,
        security_group_id=security_group_id,
        system_disk=system_disk,
        amount=amount,
        instance_charge_type=instance_charge_type,
        internet_max_bandwidth_out=internet_max_bandwidth_out
    )

    if v_switch_id:
        req.v_switch_id = v_switch_id
    if zone_id:
        req.zone_id = zone_id
    if instance_name:
        req.instance_name = instance_name
    if host_name:
        req.host_name = host_name
    if password:
        req.password = password

    runtime = util_models.RuntimeOptions()
    try:
        resp = client.run_instances_with_options(req, runtime)
        if resp and resp.body:
            return MCPResult(
                success=True,
                data={
                    "instance_ids": resp.body.instance_id_sets.instance_id_set if resp.body.instance_id_sets else [],
                    "message": "实例创建成功"
                },
                request_id=resp.body.request_id
            )
        return MCPResult(success=False, error=MCPError(
            error_type=ErrorType.API_ERROR,
            message="API 返回为空",
            suggestion="请稍后重试"
        ))
    except Exception as e:
        logger.error(f"Error in run_instances: {e}")
        return MCPResult(success=False, error=parse_api_error(e, region_id))


async def start_instance(
        region_id: str = Field(description="地域 ID"),
        instance_id: str = Field(description="实例 ID，可通过 describeInstances 获取")
) -> MCPResult:
    """启动 ECS 实例"""
    if error := validate_region_id(region_id):
        return MCPResult(success=False, error=error)
    
    if not instance_id:
        return MCPResult(success=False, error=MCPError(
            error_type=ErrorType.MISSING_PARAMETER,
            parameter="instance_id",
            message="缺少必需参数: instance_id",
            suggestion="请先使用 describeInstances 查询实例列表",
            related_tools=[ToolSuggestion(
                tool_name="describeInstances",
                description="查询实例列表",
                example_params={"region_id": region_id}
            )]
        ))
    
    client = create_client(region_id)
    req = ecs_20140526_models.StartInstanceRequest(instance_id=instance_id)
    runtime = util_models.RuntimeOptions()
    try:
        resp = client.start_instance_with_options(req, runtime)
        return MCPResult(
            success=True,
            data={"message": "实例启动请求已提交"},
            request_id=resp.body.request_id if resp.body else None
        )
    except Exception as e:
        logger.error(f"Error in start_instance: {e}")
        return MCPResult(success=False, error=parse_api_error(e, region_id))


async def stop_instance(
        region_id: str = Field(description="地域 ID"),
        instance_id: str = Field(description="实例 ID"),
        force_stop: bool = Field(default=False, description="是否强制停止，强制停止可能导致数据丢失")
) -> MCPResult:
    """停止 ECS 实例"""
    if error := validate_region_id(region_id):
        return MCPResult(success=False, error=error)
    
    if not instance_id:
        return MCPResult(success=False, error=MCPError(
            error_type=ErrorType.MISSING_PARAMETER,
            parameter="instance_id",
            message="缺少必需参数: instance_id",
            suggestion="请先使用 describeInstances 查询实例列表",
            related_tools=[ToolSuggestion(
                tool_name="describeInstances",
                description="查询实例列表",
                example_params={"region_id": region_id, "status": "Running"}
            )]
        ))
    
    client = create_client(region_id)
    req = ecs_20140526_models.StopInstanceRequest(
        instance_id=instance_id,
        force_stop=force_stop
    )
    runtime = util_models.RuntimeOptions()
    try:
        resp = client.stop_instance_with_options(req, runtime)
        return MCPResult(
            success=True,
            data={"message": "实例停止请求已提交"},
            request_id=resp.body.request_id if resp.body else None
        )
    except Exception as e:
        logger.error(f"Error in stop_instance: {e}")
        return MCPResult(success=False, error=parse_api_error(e, region_id))


async def reboot_instance(
        region_id: str = Field(description="地域 ID"),
        instance_id: str = Field(description="实例 ID"),
        force_stop: bool = Field(default=False, description="是否强制重启")
) -> MCPResult:
    """重启 ECS 实例"""
    if error := validate_region_id(region_id):
        return MCPResult(success=False, error=error)
    
    if not instance_id:
        return MCPResult(success=False, error=MCPError(
            error_type=ErrorType.MISSING_PARAMETER,
            parameter="instance_id",
            message="缺少必需参数: instance_id",
            suggestion="请先使用 describeInstances 查询实例列表"
        ))
    
    client = create_client(region_id)
    req = ecs_20140526_models.RebootInstanceRequest(
        instance_id=instance_id,
        force_stop=force_stop
    )
    runtime = util_models.RuntimeOptions()
    try:
        resp = client.reboot_instance_with_options(req, runtime)
        return MCPResult(
            success=True,
            data={"message": "实例重启请求已提交"},
            request_id=resp.body.request_id if resp.body else None
        )
    except Exception as e:
        logger.error(f"Error in reboot_instance: {e}")
        return MCPResult(success=False, error=parse_api_error(e, region_id))


async def delete_instance(
        region_id: str = Field(description="地域 ID"),
        instance_id: str = Field(description="实例 ID"),
        force: bool = Field(default=False, description="是否强制删除运行中的实例，此操作不可逆！")
) -> MCPResult:
    """删除 ECS 实例 - 此操作不可逆！"""
    if error := validate_region_id(region_id):
        return MCPResult(success=False, error=error)
    
    if not instance_id:
        return MCPResult(success=False, error=MCPError(
            error_type=ErrorType.MISSING_PARAMETER,
            parameter="instance_id",
            message="缺少必需参数: instance_id",
            suggestion="请先使用 describeInstances 查询实例列表"
        ))
    
    client = create_client(region_id)
    req = ecs_20140526_models.DeleteInstanceRequest(
        instance_id=instance_id,
        force=force
    )
    runtime = util_models.RuntimeOptions()
    try:
        resp = client.delete_instance_with_options(req, runtime)
        return MCPResult(
            success=True,
            data={"message": "实例删除请求已提交"},
            request_id=resp.body.request_id if resp.body else None
        )
    except Exception as e:
        logger.error(f"Error in delete_instance: {e}")
        return MCPResult(success=False, error=parse_api_error(e, region_id))


# =============================================================================
# 资源查询工具 - 用于支持其他工具的参数获取
# =============================================================================
async def describe_regions() -> MCPResult:
    """查询可用地域列表"""
    client = create_client()
    req = ecs_20140526_models.DescribeRegionsRequest()
    runtime = util_models.RuntimeOptions()
    try:
        resp = client.describe_regions_with_options(req, runtime)
        if resp and resp.body and resp.body.regions:
            regions = resp.body.regions.region or []
            return MCPResult(success=True, data=[
                RegionInfo(
                    RegionId=r.region_id,
                    LocalName=r.local_name,
                    RegionEndpoint=r.region_endpoint
                )
                for r in regions
            ], request_id=resp.body.request_id)
        return MCPResult(success=True, data=[])
    except Exception as e:
        logger.error(f"Error in describe_regions: {e}")
        return MCPResult(success=False, error=MCPError(
            error_type=ErrorType.API_ERROR,
            message=f"查询地域失败: {str(e)}",
            suggestion="请检查网络连接或稍后重试"
        ))


async def describe_zones(
        region_id: str = Field(description="地域 ID")
) -> MCPResult:
    """查询指定地域的可用区列表"""
    if error := validate_region_id(region_id):
        return MCPResult(success=False, error=error)
    
    client = create_client(region_id)
    req = ecs_20140526_models.DescribeZonesRequest(region_id=region_id)
    runtime = util_models.RuntimeOptions()
    try:
        resp = client.describe_zones_with_options(req, runtime)
        if resp and resp.body and resp.body.zones:
            zones = resp.body.zones.zone or []
            return MCPResult(success=True, data=[
                ZoneInfo(ZoneId=z.zone_id, LocalName=z.local_name)
                for z in zones
            ], request_id=resp.body.request_id)
        return MCPResult(success=True, data=[])
    except Exception as e:
        logger.error(f"Error in describe_zones: {e}")
        return MCPResult(success=False, error=parse_api_error(e, region_id))


async def describe_instance_types(
        region_id: str = Field(description="地域 ID"),
        instance_type_family: Optional[str] = Field(default=None, description="实例规格族，如 ecs.g7, ecs.c7"),
        cpu_core_count: Optional[int] = Field(default=None, description="CPU 核数筛选"),
        memory_size: Optional[float] = Field(default=None, description="内存大小筛选 (GB)")
) -> MCPResult:
    """查询可用的实例规格列表"""
    if error := validate_region_id(region_id):
        return MCPResult(success=False, error=error)
    
    client = create_client(region_id)
    req = ecs_20140526_models.DescribeInstanceTypesRequest()
    if instance_type_family:
        req.instance_type_family = instance_type_family
    
    runtime = util_models.RuntimeOptions()
    try:
        resp = client.describe_instance_types_with_options(req, runtime)
        if resp and resp.body and resp.body.instance_types:
            types = resp.body.instance_types.instance_type or []
            result = []
            for t in types:
                # 应用筛选条件
                if cpu_core_count and t.cpu_core_count != cpu_core_count:
                    continue
                if memory_size and t.memory_size != memory_size:
                    continue
                result.append(InstanceTypeInfo(
                    InstanceTypeId=t.instance_type_id,
                    InstanceTypeFamily=t.instance_type_family,
                    CpuCoreCount=t.cpu_core_count,
                    MemorySize=t.memory_size,
                    LocalStorageCategory=t.local_storage_category
                ))
            return MCPResult(success=True, data=result[:50], request_id=resp.body.request_id)  # 限制返回数量
        return MCPResult(success=True, data=[])
    except Exception as e:
        logger.error(f"Error in describe_instance_types: {e}")
        return MCPResult(success=False, error=parse_api_error(e, region_id))


async def describe_images(
        region_id: str = Field(description="地域 ID"),
        image_owner_alias: str = Field(default="system", description="镜像来源: system(公共镜像), self(自定义镜像), marketplace(镜像市场)"),
        os_type: Optional[str] = Field(default=None, description="操作系统类型: linux, windows"),
        image_name: Optional[str] = Field(default=None, description="镜像名称，支持模糊匹配"),
        page_size: int = Field(default=20, description="每页数量")
) -> MCPResult:
    """查询可用的镜像列表"""
    if error := validate_region_id(region_id):
        return MCPResult(success=False, error=error)
    
    client = create_client(region_id)
    req = ecs_20140526_models.DescribeImagesRequest(
        region_id=region_id,
        image_owner_alias=image_owner_alias,
        page_size=page_size
    )
    if os_type:
        req.ostype = os_type
    if image_name:
        req.image_name = image_name
    
    runtime = util_models.RuntimeOptions()
    try:
        resp = client.describe_images_with_options(req, runtime)
        if resp and resp.body and resp.body.images:
            images = resp.body.images.image or []
            return MCPResult(success=True, data=[
                ImageInfo(
                    ImageId=img.image_id,
                    ImageName=img.image_name,
                    OSName=img.osname,
                    OSType=img.ostype,
                    Platform=img.platform,
                    Size=img.size
                )
                for img in images
            ], request_id=resp.body.request_id)
        return MCPResult(success=True, data=[])
    except Exception as e:
        logger.error(f"Error in describe_images: {e}")
        return MCPResult(success=False, error=parse_api_error(e, region_id))


async def describe_security_groups(
        region_id: str = Field(description="地域 ID"),
        vpc_id: Optional[str] = Field(default=None, description="VPC ID，用于筛选特定 VPC 下的安全组"),
        security_group_name: Optional[str] = Field(default=None, description="安全组名称，支持模糊匹配")
) -> MCPResult:
    """查询可用的安全组列表"""
    if error := validate_region_id(region_id):
        return MCPResult(success=False, error=error)
    
    client = create_client(region_id)
    req = ecs_20140526_models.DescribeSecurityGroupsRequest(region_id=region_id)
    if vpc_id:
        req.vpc_id = vpc_id
    if security_group_name:
        req.security_group_name = security_group_name
    
    runtime = util_models.RuntimeOptions()
    try:
        resp = client.describe_security_groups_with_options(req, runtime)
        if resp and resp.body and resp.body.security_groups:
            groups = resp.body.security_groups.security_group or []
            return MCPResult(success=True, data=[
                SecurityGroupInfo(
                    SecurityGroupId=g.security_group_id,
                    SecurityGroupName=g.security_group_name,
                    Description=g.description,
                    VpcId=g.vpc_id
                )
                for g in groups
            ], request_id=resp.body.request_id)
        return MCPResult(success=True, data=[])
    except Exception as e:
        logger.error(f"Error in describe_security_groups: {e}")
        return MCPResult(success=False, error=parse_api_error(e, region_id))


async def describe_vswitches(
        region_id: str = Field(description="地域 ID"),
        vpc_id: Optional[str] = Field(default=None, description="VPC ID"),
        zone_id: Optional[str] = Field(default=None, description="可用区 ID，用于筛选特定可用区的交换机")
) -> MCPResult:
    """查询可用的交换机列表"""
    if error := validate_region_id(region_id):
        return MCPResult(success=False, error=error)
    
    client = create_client(region_id)
    req = ecs_20140526_models.DescribeVSwitchesRequest(region_id=region_id)
    if vpc_id:
        req.vpc_id = vpc_id
    if zone_id:
        req.zone_id = zone_id
    
    runtime = util_models.RuntimeOptions()
    try:
        resp = client.describe_vswitches_with_options(req, runtime)
        if resp and resp.body and resp.body.v_switches:
            switches = resp.body.v_switches.v_switch or []
            return MCPResult(success=True, data=[
                VSwitchInfo(
                    VSwitchId=s.v_switch_id,
                    VSwitchName=s.v_switch_name,
                    ZoneId=s.zone_id,
                    VpcId=s.vpc_id,
                    CidrBlock=s.cidr_block,
                    AvailableIpAddressCount=s.available_ip_address_count
                )
                for s in switches
            ], request_id=resp.body.request_id)
        return MCPResult(success=True, data=[])
    except Exception as e:
        logger.error(f"Error in describe_vswitches: {e}")
        return MCPResult(success=False, error=parse_api_error(e, region_id))


# =============================================================================
# ToolRegistry Class - 工具注册
# =============================================================================
class ToolRegistry:
    def __init__(self, mcp_instance: FastMCP):
        self.mcp = mcp_instance

    def register_tools(self) -> FastMCP:
        """注册所有 MCP 工具"""
        self._register_query_tools()
        self._register_lifecycle_tools()
        self._register_resource_tools()
        return self.mcp

    def _register_query_tools(self):
        """注册查询类工具"""
        self.mcp.tool(
            name="describeInstances",
            description="查询 ECS 实例列表。如果不确定地域，请先调用 describeRegions",
            annotations={"title": "查询 ECS 实例列表", "readOnlyHint": True}
        )(describe_instances)

        self.mcp.tool(
            name="describeInstanceAttribute",
            description="获取指定 ECS 实例的详细属性信息",
            annotations={"title": "获取 ECS 实例详情", "readOnlyHint": True}
        )(describe_instance_attribute)

    def _register_lifecycle_tools(self):
        """注册生命周期管理工具"""
        self.mcp.tool(
            name="runInstances",
            description=(
                "创建 ECS 实例。创建前需要准备: "
                "1) region_id - 可通过 describeRegions 查询; "
                "2) image_id - 可通过 describeImages 查询; "
                "3) instance_type - 可通过 describeInstanceTypes 查询; "
                "4) security_group_id - 可通过 describeSecurityGroups 查询; "
                "5) v_switch_id - 可通过 describeVSwitches 查询 (VPC 网络必填)"
            ),
            annotations={"title": "创建 ECS 实例", "readOnlyHint": False, "destructiveHint": False}
        )(run_instances)

        self.mcp.tool(
            name="startInstance",
            description="启动一台已停止的 ECS 实例",
            annotations={"title": "启动 ECS 实例", "readOnlyHint": False, "destructiveHint": False}
        )(start_instance)

        self.mcp.tool(
            name="stopInstance",
            description="停止一台运行中的 ECS 实例。注意：强制停止可能导致数据丢失",
            annotations={"title": "停止 ECS 实例", "readOnlyHint": False, "destructiveHint": True}
        )(stop_instance)

        self.mcp.tool(
            name="rebootInstance",
            description="重启一台 ECS 实例",
            annotations={"title": "重启 ECS 实例", "readOnlyHint": False, "destructiveHint": True}
        )(reboot_instance)

        self.mcp.tool(
            name="deleteInstance",
            description="删除一台 ECS 实例。警告：此操作不可逆！",
            annotations={"title": "删除 ECS 实例", "readOnlyHint": False, "destructiveHint": True}
        )(delete_instance)

    def _register_resource_tools(self):
        """注册资源查询工具 - 这些工具用于获取其他工具所需的参数"""
        self.mcp.tool(
            name="describeRegions",
            description="查询阿里云 ECS 可用的地域列表。在使用其他工具前，如果不确定 region_id，应先调用此工具",
            annotations={"title": "查询可用地域", "readOnlyHint": True}
        )(describe_regions)

        self.mcp.tool(
            name="describeZones",
            description="查询指定地域下的可用区列表",
            annotations={"title": "查询可用区", "readOnlyHint": True}
        )(describe_zones)

        self.mcp.tool(
            name="describeInstanceTypes",
            description="查询可用的实例规格列表。创建实例时如果不确定 instance_type，应先调用此工具",
            annotations={"title": "查询实例规格", "readOnlyHint": True}
        )(describe_instance_types)

        self.mcp.tool(
            name="describeImages",
            description="查询可用的镜像列表。创建实例时如果不确定 image_id，应先调用此工具",
            annotations={"title": "查询镜像列表", "readOnlyHint": True}
        )(describe_images)

        self.mcp.tool(
            name="describeSecurityGroups",
            description="查询可用的安全组列表。创建实例时如果不确定 security_group_id，应先调用此工具",
            annotations={"title": "查询安全组", "readOnlyHint": True}
        )(describe_security_groups)

        self.mcp.tool(
            name="describeVSwitches",
            description="查询可用的交换机列表。创建 VPC 网络实例时如果不确定 v_switch_id，应先调用此工具",
            annotations={"title": "查询交换机", "readOnlyHint": True}
        )(describe_vswitches)


# =============================================================================
# Lifespan Function
# =============================================================================
@asynccontextmanager
async def lifespan(app: FastMCP) -> AsyncGenerator[None, None]:
    logger.info("Initializing ECS MCP Server via lifespan")

    if not hasattr(app, 'state') or app.state is None:
        class AppState:
            pass
        app.state = AppState()

    app.state.default_region_id = os.getenv("ECS_DEFAULT_REGION", "cn-hangzhou")
    logger.info(f"Default region: {app.state.default_region_id}")

    registry = ToolRegistry(mcp_instance=app)
    registry.register_tools()

    yield

    logger.info("Shutting down ECS MCP Server via lifespan")


# =============================================================================
# FastMCP Instance Creation & Server Run
# =============================================================================
mcp = FastMCP(
    "ECSManagementAssistant",
    lifespan=lifespan,
    instructions=(
        "ECS Management Assistant 是一个用于管理阿里云 ECS 实例的工具集。\n\n"
        "**工具使用指南**:\n"
        "1. 查询地域: 使用 describeRegions 获取可用地域列表\n"
        "2. 查询实例: 使用 describeInstances 获取实例列表\n"
        "3. 创建实例前准备:\n"
        "   - describeRegions -> 获取 region_id\n"
        "   - describeImages -> 获取 image_id\n"
        "   - describeInstanceTypes -> 获取 instance_type\n"
        "   - describeSecurityGroups -> 获取 security_group_id\n"
        "   - describeVSwitches -> 获取 v_switch_id (VPC 必填)\n"
        "4. 创建实例: 使用 runInstances\n\n"
        "**错误处理**: 所有工具返回统一的 MCPResult 格式，失败时包含错误类型、建议和相关工具推荐。"
    ),
    host=os.getenv("SERVER_HOST", "0.0.0.0"),
    port=int(os.getenv("SERVER_PORT", "8000"))
)


def run_server():
    log_level_str = os.getenv("LOG_LEVEL", "INFO").upper()
    logging.basicConfig(level=log_level_str, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    logger.info(f"Starting ECS MCP server with log level {log_level_str}")
    mcp.run(transport=os.getenv('SERVER_TRANSPORT', 'stdio'))


if __name__ == "__main__":
    run_server()

