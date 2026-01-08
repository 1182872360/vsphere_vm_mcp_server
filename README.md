# vSphere VM MCP Server

基于最佳实践实现的 vSphere 虚拟机创建 MCP 服务器，参考了阿里云 ECS MCP 服务器的架构模式。

## ✨ 特性

- **结构化错误处理** - 使用 `ErrorType` 枚举和 `MCPError` 模型
- **统一响应模型** - `MCPResult` 确保所有工具响应格式一致
- **详细参数验证** - 每个参数都有专门的验证函数
- **智能错误解析** - 将 vSphere API 错误转换为 LLM 友好的格式
- **工具注册模式** - 使用 `ToolRegistry` 类管理工具注册
- **生命周期管理** - 使用 `lifespan` 函数进行初始化和清理

## 🚀 快速开始

### 安装方式

#### 1. 使用 uvx 直接从 GitHub 运行（推荐）

```bash
# 直接运行（无需本地安装）
uvx --from git+https://github.com/your-username/vsphere-vm-mcp-server.git vsphere-vm-mcp-server

# 或者指定分支/标签
uvx --from git+https://github.com/your-username/vsphere-vm-mcp-server.git@main vsphere-vm-mcp-server
```

#### 2. 本地安装

```bash
# 克隆仓库
git clone https://github.com/your-username/vsphere-vm-mcp-server.git
cd vsphere-vm-mcp-server

# 安装依赖
pip install .

# 或者开发模式安装
pip install -e .
```

### 配置 vSphere 连接信息

通过环境变量配置 vSphere 连接：

```bash
export VSPHERE_HOST="vcenter.example.com"
export VSPHERE_USERNAME="admin"
export VSPHERE_PASSWORD="password"
export VSPHERE_PORT="443"  # 可选，默认 443
```

### 运行服务器

```bash
# 使用 uvx 运行
uvx --from git+https://github.com/your-username/vsphere-vm-mcp-server.git vsphere-vm-mcp-server

# 或者本地安装后运行
vsphere-vm-mcp-server

# 自定义配置
SERVER_PORT=9000 LOG_LEVEL=DEBUG vsphere-vm-mcp-server
```

## 🛠️ 可用工具

### 查询工具

| 工具名称 | 描述 | 参数 |
|---------|------|------|
| `describeTemplates` | 查询可用的虚拟机模板列表 | `cluster_name` (可选) |
| `describeHosts` | 查询 ESXi 主机列表及资源使用情况 | `cluster_name` (可选) |
| `describeClusters` | 查询可用的集群列表 | 无 |
| `describeFolders` | 查询可用的文件夹列表 | 无 |
| `describeResourcePools` | 查询可用的资源池列表 | `cluster_name` (可选) |
| `describeVMs` | 查询虚拟机列表 | `cluster_name` (可选), `vm_name` (可选) |

### 生命周期工具

| 工具名称 | 描述 | 必需参数 | 可选参数 |
|---------|------|----------|----------|
| `createVMFromTemplate` | 从模板创建虚拟机 | `vm_name`, `template_name`, `cluster_name` | `cpu`, `memory_mb`, `folder_name`, `resource_pool_name` |

## 📋 使用示例

### 典型虚拟机创建流程

```bash
# 1. 查询可用模板
describeTemplates()

# 2. 查询可用集群
describeClusters()

# 3. 创建虚拟机
createVMFromTemplate(
    vm_name="web-server-01",
    template_name="ubuntu-20.04-template",
    cluster_name="Cluster01",
    cpu=4,
    memory_mb=8192,
    folder_name="Production"
)
```

### 错误处理示例

当参数错误时，服务器会返回结构化的错误信息：

```json
{
  "success": false,
  "error": {
    "error_type": "MISSING_PARAMETER",
    "parameter": "vm_name",
    "message": "缺少必需参数: vm_name (虚拟机名称)",
    "suggestion": "请提供有效的虚拟机名称，如 'web-server-01'",
    "related_tools": null
  }
}
```

## 🔧 环境变量配置

| 变量名 | 描述 | 默认值 | 必需 |
|--------|------|--------|------|
| `VSPHERE_HOST` | vSphere 主机地址 | - | ✅ |
| `VSPHERE_USERNAME` | vSphere 用户名 | - | ✅ |
| `VSPHERE_PASSWORD` | vSphere 密码 | - | ✅ |
| `VSPHERE_PORT` | vSphere 端口 | 443 | ❌ |
| `SERVER_HOST` | 服务器监听地址 | 0.0.0.0 | ❌ |
| `SERVER_PORT` | 服务器监听端口 | 8000 | ❌ |
| `SERVER_TRANSPORT` | 传输协议 (stdio/sse/http) | stdio | ❌ |
| `LOG_LEVEL` | 日志级别 (DEBUG/INFO/WARNING/ERROR) | INFO | ❌ |

## 📦 依赖要求

- Python >= 3.13
- mcp[cli] >= 1.25.0
- pydantic >= 2.12.5
- pyvmomi >= 8.0.0

## 🏗️ 项目结构

```
vsphere-vm-mcp-server/
├── main.py                 # 主入口模块
├── pyproject.toml         # 项目配置
├── README.md              # 说明文档
└── requirements.txt       # 依赖列表（可选）
```

### main.py 核心组件

- **错误类型定义** (`ErrorType`) - 9种错误类型
- **响应模型** (`MCPResult`, `MCPError`) - 统一响应格式
- **数据模型** (`VMInfo`, `VMTemplateInfo` 等) - 业务数据结构
- **参数验证** (`validate_*` 函数) - 详细的参数检查
- **错误解析** (`parse_vsphere_error`) - 智能错误转换
- **工具注册** (`ToolRegistry`) - 工具管理类
- **生命周期** (`lifespan`) - 服务器生命周期管理
- **核心 API** (`describe_*`, `create_vm_from_template`) - 业务逻辑

## 🔍 故障排除

### 常见问题

1. **连接失败**
   ```bash
   # 检查 vSphere 配置
   echo $VSPHERE_HOST
   echo $VSPHERE_USERNAME
   echo $VSPHERE_PASSWORD

   # 测试网络连接
   ping $VSPHERE_HOST
   ```

2. **依赖缺失**
   ```bash
   # 重新安装依赖
   pip install --force-reinstall .
   ```

3. **权限问题**
   ```bash
   # 检查 vSphere 用户权限
   # 确保用户有虚拟机创建权限
   ```

### 日志调试

```bash
# 启用调试日志
LOG_LEVEL=DEBUG vsphere-vm-mcp-server

# 查看详细错误信息
# 日志会显示详细的连接、验证和操作过程
```

## 🤝 贡献指南

欢迎提交 Issue 和 Pull Request！

## 📄 许可证

MIT License

## 🙏 致谢

参考了阿里云 ECS MCP 服务器的最佳实践模式。