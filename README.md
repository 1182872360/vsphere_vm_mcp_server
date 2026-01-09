# vSphere VM MCP Server

基于最佳实践实现的 vSphere 虚拟机管理 MCP 服务器，可作为 MCP 服务开发的参考案例。

## ✨ 特性

- **工程化项目结构** - 清晰的模块划分，便于维护和扩展
- **结构化错误处理** - 使用 `ErrorType` 枚举和 `MCPError` 模型
- **统一响应模型** - `MCPResult` 确保所有工具响应格式一致
- **详细参数验证** - 独立的验证模块，职责单一
- **智能错误解析** - 将 vSphere API 错误转换为 LLM 友好的格式
- **工具注册模式** - 使用 `ToolRegistry` 类管理工具注册

## 🚀 快速开始

### 安装

```bash
# 使用 uv 安装
uv pip install .

# 或开发模式
uv pip install -e .
```

### 配置环境变量

```bash
export VSPHERE_HOST="vcenter.example.com"
export VSPHERE_USERNAME="administrator@vsphere.local"
export VSPHERE_PASSWORD="your-password"
export VSPHERE_PORT="443"  # 可选，默认 443
```

### 运行服务器

```bash
# 标准运行
uv run vsphere-vm-mcp-server

# 自定义配置
LOG_LEVEL=DEBUG SERVER_PORT=9000 uv run vsphere-vm-mcp-server
```

## 🛠️ 可用工具

### 查询工具

| 工具名称 | 描述 | 参数 |
|---------|------|------|
| `describeTemplates` | 查询虚拟机模板列表 | `cluster_name` (可选) |
| `describeHosts` | 查询 ESXi 主机列表 | `cluster_name` (可选) |
| `describeClusters` | 查询集群列表 | 无 |
| `describeFolders` | 查询文件夹列表 | 无 |
| `describeResourcePools` | 查询资源池列表 | `cluster_name` (可选) |
| `describeNetworks` | 查询网络列表 | `cluster_name` (可选) |
| `describeVMs` | 查询虚拟机列表 | `cluster_name`, `vm_name` (可选) |
| `getVMPowerState` | 查询虚拟机电源状态 | `vm_name` |

### 生命周期工具

| 工具名称 | 描述 | 必需参数 | 可选参数 |
|---------|------|----------|----------|
| `createVMFromTemplate` | 从模板创建虚拟机 | `vm_name`, `template_name`, `cluster_name` | `cpu`, `memory_mb`, `network_name`, `folder_name`, `resource_pool_name` |
| `reconfigureVM` | 重新配置虚拟机 | `vm_name` | `cpu`, `memory_mb`, `disk_size_gb`, `network_name` |

## 📦 项目结构

```
vsphere_vm_mcp_server/
├── pyproject.toml
├── README.md
├── docs/
│   └── BEST_PRACTICES.md      # 最佳实践文档
└── src/vsphere_mcp/
    ├── __init__.py            # 包导出
    ├── server.py              # MCP 服务器入口
    ├── models/                # 数据模型
    ├── client/                # vSphere 客户端
    ├── tools/                 # MCP 工具
    └── utils/                 # 工具函数
```

## 🔧 环境变量

| 变量名 | 描述 | 默认值 | 必需 |
|--------|------|--------|------|
| `VSPHERE_HOST` | vSphere 主机地址 | - | ✅ |
| `VSPHERE_USERNAME` | vSphere 用户名 | - | ✅ |
| `VSPHERE_PASSWORD` | vSphere 密码 | - | ✅ |
| `VSPHERE_PORT` | vSphere 端口 | 443 | ❌ |
| `SERVER_HOST` | 监听地址 | 0.0.0.0 | ❌ |
| `SERVER_PORT` | 监听端口 | 8000 | ❌ |
| `SERVER_TRANSPORT` | 传输协议 | stdio | ❌ |
| `LOG_LEVEL` | 日志级别 | INFO | ❌ |