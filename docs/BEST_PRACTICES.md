# MCP 服务开发最佳实践

本文档总结了开发 MCP (Model Context Protocol) 服务器的最佳实践，基于 vSphere VM MCP Server 的实现经验。

## 1. 项目结构

采用 `src` 布局，模块职责清晰：

```
src/your_mcp/
├── __init__.py       # 包导出
├── server.py         # MCP 服务器入口
├── models/           # 数据模型
├── client/           # 外部 API 客户端
├── tools/            # MCP 工具函数
└── utils/            # 工具函数（验证、错误处理）
```

### 模块职责

| 模块 | 职责 | 示例内容 |
|------|------|----------|
| `models/` | 数据结构定义 | Pydantic 模型、枚举 |
| `client/` | 封装外部 API | API 客户端类、连接管理 |
| `tools/` | MCP 工具实现 | async 工具函数 |
| `utils/` | 通用工具 | 验证函数、错误解析 |
| `server.py` | 入口点 | FastMCP 实例、工具注册 |

---

## 2. 统一响应模型

**所有工具必须返回统一的响应格式**，便于 LLM 解析：

```python
class MCPResult(BaseModel):
    success: bool                    # 操作是否成功
    data: Optional[Any] = None       # 成功时的数据
    error: Optional[MCPError] = None # 失败时的错误信息
    request_id: Optional[str] = None # 请求追踪 ID
```

### 示例

```python
# 成功响应
return MCPResult(success=True, data=templates)

# 失败响应
return MCPResult(success=False, error=MCPError(...))
```

---

## 3. 结构化错误处理

### 3.1 错误类型枚举

定义明确的错误类型，帮助 LLM 理解错误性质：

```python
class ErrorType(str, Enum):
    MISSING_PARAMETER = "MISSING_PARAMETER"    # 必需参数缺失
    INVALID_PARAMETER = "INVALID_PARAMETER"    # 参数格式或值无效
    RESOURCE_NOT_FOUND = "RESOURCE_NOT_FOUND"  # 资源不存在
    PERMISSION_DENIED = "PERMISSION_DENIED"    # 权限不足
    QUOTA_EXCEEDED = "QUOTA_EXCEEDED"          # 配额超限
    DEPENDENCY_MISSING = "DEPENDENCY_MISSING"  # 依赖资源缺失
    API_ERROR = "API_ERROR"                    # API 调用错误
    CONNECTION_ERROR = "CONNECTION_ERROR"      # 连接错误
```

### 3.2 错误响应模型

```python
class MCPError(BaseModel):
    error_type: ErrorType      # 错误类型
    message: str               # 人类可读描述
    parameter: Optional[str]   # 出错的参数名
    suggestion: str            # 解决方案建议
    related_tools: Optional[List[ToolSuggestion]]  # 相关工具推荐
```

### 3.3 工具建议

引导 LLM 调用正确的工具解决问题：

```python
class ToolSuggestion(BaseModel):
    tool_name: str                        # 工具名称
    description: str                      # 调用原因
    example_params: Optional[Dict] = None # 示例参数

# 使用示例
TOOL_DESCRIBE_TEMPLATES = ToolSuggestion(
    tool_name="describeTemplates",
    description="查询可用的虚拟机模板列表",
    example_params={"cluster_name": "Cluster01"}
)
```

---

## 4. 参数验证

### 4.1 独立验证函数

每个参数有专门的验证函数，返回 `Optional[MCPError]`：

```python
def validate_vm_name(vm_name: Optional[str]) -> Optional[MCPError]:
    if not vm_name:
        return MCPError(
            error_type=ErrorType.MISSING_PARAMETER,
            parameter="vm_name",
            message="缺少必需参数: vm_name",
            suggestion="请提供有效的虚拟机名称"
        )
    
    if len(vm_name) < 3 or len(vm_name) > 80:
        return MCPError(
            error_type=ErrorType.INVALID_PARAMETER,
            parameter="vm_name",
            message="虚拟机名称长度必须在 3-80 字符之间",
            suggestion="请调整名称长度"
        )
    
    return None  # 验证通过
```

### 4.2 验证链模式

在工具函数开头使用验证链：

```python
async def create_vm_from_template(vm_name: str, ...) -> MCPResult:
    # 参数验证链
    if error := validate_vm_name(vm_name):
        return MCPResult(success=False, error=error)
    
    if error := validate_template_name(template_name):
        return MCPResult(success=False, error=error)
    
    # 验证通过，执行业务逻辑
    ...
```

---

## 5. 错误解析

将底层 API 错误转换为 LLM 友好的格式：

```python
def parse_vsphere_error(error: Exception, operation: str) -> MCPError:
    error_msg = str(error)
    
    # 连接错误
    if 'connection' in error_msg.lower():
        return MCPError(
            error_type=ErrorType.CONNECTION_ERROR,
            message=f"无法连接到 vSphere: {error_msg}",
            suggestion="请检查主机地址和网络连接"
        )
    
    # 资源不存在
    if 'not found' in error_msg.lower():
        return MCPError(
            error_type=ErrorType.RESOURCE_NOT_FOUND,
            message="指定的资源不存在",
            suggestion="请使用 describe* 工具查询可用资源",
            related_tools=[TOOL_DESCRIBE_TEMPLATES]
        )
    
    # 默认错误
    return MCPError(
        error_type=ErrorType.API_ERROR,
        message=f"操作失败: {error_msg}",
        suggestion="请检查参数或稍后重试"
    )
```

---

## 6. 工具注册

使用 `ToolRegistry` 类集中管理工具注册：

```python
class ToolRegistry:
    def __init__(self, mcp_instance):
        self.mcp = mcp_instance

    def register_tools(self):
        self._register_query_tools()
        self._register_lifecycle_tools()
        return self.mcp

    def _register_query_tools(self):
        self.mcp.tool(
            name="describeTemplates",
            description="查询虚拟机模板列表",
            annotations={"readOnlyHint": True}
        )(describe_templates)
```

### 工具注解

```python
annotations={
    "title": "查询虚拟机模板",    # 显示标题
    "readOnlyHint": True,         # 只读操作
    "destructiveHint": False,     # 非破坏性操作
}
```

---

## 7. 客户端管理

### 7.1 全局客户端模式

使用模块级全局变量管理客户端实例：

```python
_client: Optional[MyClient] = None

def get_client() -> Tuple[Optional[MyClient], Optional[MCPError]]:
    global _client
    
    # 检查配置
    host = os.getenv("API_HOST")
    if not host:
        return None, MCPError(
            error_type=ErrorType.MISSING_PARAMETER,
            message="API 配置不完整",
            suggestion="请设置环境变量: API_HOST"
        )
    
    # 惰性连接
    if _client is None or not _client.is_connected():
        _client = MyClient(host)
        error = _client.connect()
        if error:
            _client = None
            return None, error
    
    return _client, None
```

### 7.2 在工具中使用

```python
async def describe_resources() -> MCPResult:
    client, error = get_client()
    if error:
        return MCPResult(success=False, error=error)
    
    try:
        data = client.get_resources()
        return MCPResult(success=True, data=data)
    except Exception as e:
        return MCPResult(success=False, error=parse_error(e))
```

---

## 8. 生命周期管理

使用 `lifespan` 函数进行初始化：

```python
@asynccontextmanager
async def lifespan(app) -> AsyncGenerator[None, None]:
    logger.info("初始化 MCP Server...")
    
    # 初始化应用状态
    app.state.config = load_config()
    
    # 注册工具
    registry = ToolRegistry(app)
    registry.register_tools()
    
    yield  # 服务器运行
    
    logger.info("关闭 MCP Server...")

# 创建 FastMCP 实例
mcp = FastMCP("MyMCPServer", lifespan=lifespan)
```

---

## 9. 日志规范

```python
import logging

logger = logging.getLogger(__name__)

# 在 run_server 中配置
logging.basicConfig(
    level=getattr(logging, os.getenv("LOG_LEVEL", "INFO")),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

# 使用
logger.info("操作成功")
logger.warning(f"获取资源失败: {e}")
logger.error(f"严重错误: {e}")
```

---

## 10. 检查清单

开发新的 MCP 服务时，确保：

- [ ] 采用 `src` 布局的项目结构
- [ ] 定义 `ErrorType` 枚举和 `MCPError` 模型
- [ ] 所有工具返回 `MCPResult`
- [ ] 每个参数有独立的验证函数
- [ ] API 错误转换为 LLM 友好格式
- [ ] 使用 `ToolRegistry` 集中注册工具
- [ ] 实现全局客户端管理
- [ ] 配置 `lifespan` 生命周期函数
- [ ] 添加适当的日志记录
- [ ] 更新 `pyproject.toml` 入口点
