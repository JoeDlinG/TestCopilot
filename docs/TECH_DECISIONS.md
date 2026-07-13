# AITestLab 技术决策文档

## 1. 技术选型决策

### 1.1 后端框架：FastAPI

| 维度 | 评估 |
|------|------|
| **选型理由** | 原生异步支持（asyncio），硬件通信需要大量异步 I/O；自动生成 OpenAPI 文档；Pydantic 数据验证与 PRD 中的 Schema 设计天然契合；性能优于 Flask/Django |
| **替代方案** | Flask：同步模型，需要额外扩展才能支持 WebSocket 和异步；Django：过重，ORM 与 SQLite 配合不如 SQLAlchemy 灵活 |
| **风险** | 无显著风险 |

### 1.2 前端框架：React 18 + TypeScript

| 维度 | 评估 |
|------|------|
| **选型理由** | PRD 指定；生态成熟，Ant Design 和 ReactFlow 均有完整 React 支持；TypeScript 提供类型安全，减少运行时错误 |
| **替代方案** | Vue 3：生态同样成熟，但 ReactFlow 的 Vue 版本功能落后于 React 版 |
| **风险** | 无显著风险 |

### 1.3 数据库：SQLite

| 维度 | 评估 |
|------|------|
| **选型理由** | 零配置部署，适合桌面级测试工具；单文件数据库便于备份和迁移；SQLAlchemy ORM 抽象层确保未来可切换 PostgreSQL |
| **替代方案** | PostgreSQL：功能强大但需要独立部署，增加运维复杂度 |
| **风险** | 并发写入性能有限，不适合超过 50 台设备同时测试的场景。缓解：WAL 模式 + 合理的事务设计 |
| **决策** | Phase 1-5 使用 SQLite，Phase 6+ 评估是否需要迁移到 PostgreSQL |

### 1.4 通信库选择

| 协议 | 库 | 选型理由 |
|------|-----|----------|
| SCPI/VISA | PyVISA + PyVISA-py | 业界标准，支持 USB/GPIB/以太网，PyVISA-py 提供纯 Python 后端无需 NI-VISA 驱动 |
| CAN | python-can | 支持 PCAN、Vector、SocketCAN、Kvaser 等主流接口 |
| 串口 | pyserial | 成熟稳定，支持 RS232/RS485，异步支持好 |
| 以太网 | asyncio (标准库) | 原生异步 TCP/UDP，与 FastAPI 异步模型一致 |

### 1.5 AI 集成库

| 库 | 用途 | 选型理由 |
|------|------|----------|
| httpx | 通用 HTTP 客户端 | 异步支持，连接池管理，用于调用 Ollama/LocalAI/vLLM 等本地模型 API |
| openai SDK | OpenAI 兼容 API | 标准库，腾讯混元、阿里通义千问、百度文心一言等均提供 OpenAI 兼容接口 |

### 1.6 报告生成

| 库 | 用途 | 选型理由 |
|------|------|----------|
| Jinja2 | 模板引擎 | Python 最流行的模板引擎，与 HTML/XML 报告天然契合 |
| WeasyPrint | HTML→PDF 转换 | 纯 Python，无外部依赖，CSS 排版质量好 |
| python-docx | DOCX 生成 | 如需原生 DOCX 格式 |

### 1.7 前端状态管理：Zustand

| 维度 | 评估 |
|------|------|
| **选型理由** | 极简 API，TypeScript 支持优秀，无 boilerplate；比 Redux 轻量，比 Context 性能好；适合中小型应用 |
| **替代方案** | Redux Toolkit：功能完整但过于重型；Jotai：同样优秀但社区略小 |
| **风险** | 无显著风险，如需更复杂的状态管理可在 Phase 3+ 引入 Redux Toolkit |

### 1.8 前端数据获取：TanStack Query (React Query)

| 维度 | 评估 |
|------|------|
| **选型理由** | 自动缓存、重新获取、乐观更新；与 REST API 完美配合；减少大量手写 loading/error 状态代码 |
| **替代方案** | SWR：功能类似但不如 React Query 灵活；手写 useEffect：代码冗余且易出错 |
| **风险** | 无显著风险 |

### 1.9 构建工具：Vite

| 维度 | 评估 |
|------|------|
| **选型理由** | 极快的 HMR，开发体验优秀；TypeScript 原生支持；Rollup 打包产物小 |
| **替代方案** | CRA (Create React App)：已不推荐，维护停滞；Webpack：配置复杂 |
| **风险** | 无显著风险 |

---

## 2. 数据序列化方案：通信日志高效存储

### 2.1 问题分析

测试场景下通信日志量大（每秒可能数十条），需要高效存储和快速检索：
- 每条日志包含时间戳、设备、方向、原始数据（文本+十六进制）
- 单次测试执行可能产生数千条日志
- 需要支持按时间范围、设备、执行 ID 多维查询

### 2.2 方案设计

#### 存储策略

```
┌──────────────────────────────────────────────────┐
│              分层存储架构                          │
│                                                   │
│  Layer 1: 内存缓冲区 (asyncio.Queue)              │
│  ├─ 实时写入缓冲，批量刷盘                         │
│  ├─ 缓冲区大小: 1000 条                            │
│  └─ 刷盘间隔: 1 秒 或 缓冲区满                     │
│                                                   │
│  Layer 2: SQLite 主存储                           │
│  ├─ 结构化字段索引查询                             │
│  ├─ WAL 模式提升并发写入                          │
│  └─ 定期 VACUUM 清理                              │
│                                                   │
│  Layer 3: CSV 归档导出                            │
│  ├─ 按执行 ID 导出                                │
│  ├─ 按日期归档                                    │
│  └─ 可选压缩                                      │
└──────────────────────────────────────────────────┘
```

#### 关键优化

1. **批量写入**：单条 INSERT 改为批量 INSERT，减少事务开销
```python
# 批量写入（每次最多 500 条）
async def batch_insert_logs(logs: List[CommunicationLog]):
    async with db.begin():
        for log in logs:
            db.add(log)
```

2. **WAL 模式**：SQLite 启用 WAL (Write-Ahead Logging)
```python
engine = create_engine("sqlite:///./aitestlab.db")
@event.listens_for(engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA synchronous=NORMAL")
    cursor.execute("PRAGMA cache_size=-64000")  # 64MB
    cursor.close()
```

3. **十六进制数据**：`raw_data_hex` 仅对二进制协议（CAN）存储，文本协议（SCPI）按需计算

4. **分页查询**：使用 keyset pagination（基于 timestamp + id）替代 OFFSET，大数据量下性能更好
```sql
SELECT * FROM communication_logs
WHERE (timestamp, id) > (:last_ts, :last_id)
ORDER BY timestamp DESC, id DESC
LIMIT 50
```

5. **数据保留策略**：
   - 默认保留 30 天通信日志
   - 关联执行记录的日志保留至执行记录删除
   - 定时任务清理过期日志

---

## 3. 前端状态管理方案

### 3.1 状态分层架构

```
┌──────────────────────────────────────────────┐
│              UI State (Zustand)               │
│  uiStore: sidebar, theme, modals              │
├──────────────────────────────────────────────┤
│           Server State (React Query)          │
│  devices, testcases, logs, reports, ...       │
│  - 自动缓存、重新获取                          │
│  - 乐观更新（如设备断开）                      │
├──────────────────────────────────────────────┤
│          Real-time State (WebSocket + Zustand) │
│  execution progress, device live data         │
│  - WebSocket 事件 → dispatch to store         │
├──────────────────────────────────────────────┤
│            Form State (Ant Design Form)       │
│  device config, AI model config               │
│  - 表单验证、提交、重置                        │
├──────────────────────────────────────────────┤
│            Local State (useState)              │
│  组件内部状态（输入框、展开/折叠等）            │
└──────────────────────────────────────────────┘
```

### 3.2 Zustand Store 设计

```typescript
// stores/deviceStore.ts
interface DeviceStore {
  devices: Device[];
  connectedDevices: Map<string, Device>;
  isLoading: boolean;

  setDevices: (devices: Device[]) => void;
  addDevice: (device: Device) => void;
  removeDevice: (id: string) => void;
  updateDeviceStatus: (id: string, status: DeviceStatus) => void;
}

// stores/executionStore.ts
interface ExecutionStore {
  currentExecution: Execution | null;
  stepResults: Map<number, StepResult>;
  liveData: Map<string, DeviceLiveData>;

  setExecution: (exec: Execution) => void;
  updateStepResult: (stepIndex: number, result: Partial<StepResult>) => void;
  updateLiveData: (deviceId: string, data: DeviceLiveData) => void;
  clearExecution: () => void;
}
```

### 3.3 React Query 集成

```typescript
// hooks/useDevices.ts
export function useDevices(filters?: DeviceFilters) {
  return useQuery({
    queryKey: ['devices', filters],
    queryFn: () => deviceApi.list(filters),
    staleTime: 30_000, // 30 秒内不重新获取
  });
}

// hooks/useConnectDevice.ts
export function useConnectDevice() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: deviceApi.connect,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['devices'] });
    },
  });
}
```

### 3.4 WebSocket 集成

```typescript
// hooks/useExecutionWebSocket.ts
export function useExecutionWebSocket(executionId: string) {
  const updateStepResult = useExecutionStore(s => s.updateStepResult);
  const updateLiveData = useExecutionStore(s => s.updateLiveData);

  useEffect(() => {
    const ws = new WebSocket(`ws://localhost:8000/ws/executions/${executionId}`);

    ws.onmessage = (event) => {
      const msg = JSON.parse(event.data);
      switch (msg.type) {
        case 'step_complete':
          updateStepResult(msg.data.step_index, msg.data);
          break;
        case 'device_data':
          updateLiveData(msg.data.device_id, msg.data);
          break;
      }
    };

    return () => ws.close();
  }, [executionId]);
}
```

---

## 4. 插件热加载方案

### 4.1 设计目标

1. 运行时安装/卸载插件，无需重启后端
2. 插件崩溃不影响主系统
3. 插件可以暴露自定义配置 UI
4. 支持从文件上传安装

### 4.2 实现方案

#### 加载流程

```python
# plugins/loader.py
import importlib
import importlib.util
import sys
from pathlib import Path

class PluginLoader:
    def __init__(self, plugin_dir: Path):
        self.plugin_dir = plugin_dir

    def load_plugin(self, plugin_name: str) -> Type[CommunicationPlugin]:
        """加载单个插件模块"""
        plugin_path = self.plugin_dir / plugin_name

        # 方式 1：从文件路径加载
        if plugin_path.is_file() and plugin_path.suffix == '.py':
            spec = importlib.util.spec_from_file_location(
                plugin_name, str(plugin_path)
            )
            module = importlib.util.module_from_spec(spec)
            sys.modules[plugin_name] = module
            spec.loader.exec_module(module)
            return self._find_plugin_class(module)

        # 方式 2：从包加载（__init__.py）
        elif plugin_path.is_dir():
            module = importlib.import_module(f"plugins.{plugin_name}")
            return self._find_plugin_class(module)

        raise PluginLoadError(f"Cannot load plugin: {plugin_name}")

    def reload_plugin(self, plugin_name: str) -> Type[CommunicationPlugin]:
        """热重载插件（开发模式）"""
        module = sys.modules.get(plugin_name)
        if module:
            importlib.reload(module)
        return self.load_plugin(plugin_name)

    def unload_plugin(self, plugin_name: str):
        """卸载插件模块"""
        if plugin_name in sys.modules:
            del sys.modules[plugin_name]
```

#### 插件管理器

```python
# plugins/manager.py
class PluginManager:
    def __init__(self, db: Session, plugin_dir: Path):
        self.db = db
        self.plugin_dir = plugin_dir
        self.loader = PluginLoader(plugin_dir)
        self.active_plugins: Dict[str, CommunicationPlugin] = {}
        self._lock = asyncio.Lock()

    async def install_plugin(self, file: UploadFile) -> Plugin:
        """安装插件：保存文件 + 验证 + 记录数据库"""
        # 1. 保存到 plugins/ 目录
        # 2. 加载并验证实现 CommunicationPlugin 接口
        # 3. 记录到 plugins 表
        pass

    async def enable_plugin(self, plugin_id: str) -> CommunicationPlugin:
        """启用插件：加载 + 实例化"""
        async with self._lock:
            plugin_record = self._get_plugin_record(plugin_id)
            plugin_cls = self.loader.load_plugin(plugin_record.module_name)
            instance = plugin_cls()
            self.active_plugins[plugin_id] = instance
            # 更新数据库状态
            plugin_record.status = 'enabled'
            plugin_record.enabled_at = datetime.utcnow()
            self.db.commit()
            return instance

    async def disable_plugin(self, plugin_id: str):
        """禁用插件：断开连接 + 清理"""
        async with self._lock:
            if plugin_id in self.active_plugins:
                instance = self.active_plugins.pop(plugin_id)
                await instance.disconnect()
            self.loader.unload_plugin(plugin_id)

    async def get_plugin(self, plugin_id: str) -> CommunicationPlugin:
        """获取已启用的插件实例"""
        if plugin_id not in self.active_plugins:
            raise PluginNotEnabledError(plugin_id)
        return self.active_plugins[plugin_id]
```

#### 异常隔离

```python
class SafePluginProxy:
    """插件代理，捕获所有异常防止影响主系统"""

    def __init__(self, plugin: CommunicationPlugin, plugin_id: str):
        self._plugin = plugin
        self._plugin_id = plugin_id

    async def send(self, data: bytes, timeout: float = 5.0):
        try:
            return await asyncio.wait_for(
                self._plugin.send(data),
                timeout=timeout + 5.0  # 额外 5 秒缓冲
            )
        except asyncio.TimeoutError:
            raise PluginTimeoutError(f"Plugin {self._plugin_id} send timeout")
        except Exception as e:
            logger.error(f"Plugin {self._plugin_id} send error: {e}")
            raise PluginExecutionError(str(e))
```

### 4.3 插件配置 UI 自动生成

插件通过 `config_schema` 返回 JSON Schema，前端使用 `react-jsonschema-form` 或 Ant Design 动态表单渲染：

```python
class CustomCANPlugin(CommunicationPlugin):
    @property
    def config_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "bitrate": {
                    "type": "integer",
                    "title": "波特率",
                    "default": 500000,
                    "enum": [125000, 250000, 500000, 1000000]
                },
                "sjw": {
                    "type": "integer",
                    "title": "SJW",
                    "default": 1,
                    "minimum": 1,
                    "maximum": 4
                }
            },
            "required": ["bitrate"]
        }
```

前端渲染：
```typescript
// PluginConfigForm.tsx
function PluginConfigForm({ schema, config, onSave }) {
  // 使用 @rjsf/antd 动态渲染表单
  return (
    <Form schema={schema} formData={config} onSubmit={onSave}>
      <Button type="primary" htmlType="submit">保存配置</Button>
    </Form>
  );
}
```

### 4.4 插件文件结构规范

```
plugins/
├── custom_can_protocol/
│   ├── __init__.py          # 导出 plugin_class
│   ├── plugin.py            # 实现 CommunicationPlugin
│   ├── data/                # 插件数据目录（沙箱隔离）
│   └── requirements.txt     # 插件依赖（可选）
│
├── modbus_rtu/
│   ├── __init__.py
│   └── plugin.py
│
└── simple_http_plugin.py    # 单文件插件
```

---

## 5. 关键架构决策记录 (ADR)

### ADR-001: 使用 SQLite 而非 PostgreSQL

- **状态**: 已接受
- **日期**: 2025-01-15
- **背景**: 需要选择主存储数据库
- **决策**: 使用 SQLite，通过 SQLAlchemy 抽象层确保可迁移
- **后果**: 
  - ✅ 零部署依赖，适合桌面工具
  - ✅ 单文件备份方便
  - ❌ 并发写入限制，需 WAL 模式优化
  - ❌ 未来可能需要迁移

### ADR-002: AI 模型使用统一 Provider 抽象

- **状态**: 已接受
- **日期**: 2025-01-15
- **背景**: 需要支持本地和云端多种 AI 模型
- **决策**: 定义 AIProvider 抽象基类，每个厂商实现独立 Provider
- **后果**: 
  - ✅ 新增模型仅需实现 Provider 接口
  - ✅ 上层代码与具体模型解耦
  - ❌ 不同厂商特有功能（如 function calling）需要最小公约数抽象

### ADR-003: 流程图使用 JSON 存储而非 DSL

- **状态**: 已接受
- **日期**: 2025-01-15
- **背景**: 测试流程需要可视化编辑和持久化
- **决策**: 流程图以 JSON 格式存储在 test_flows 表中（nodes + edges），由 ReactFlow 渲染
- **替代方案**: 自定义 DSL → 不适合可视化编辑
- **后果**: 
  - ✅ 前端直接解析渲染，无需转换
  - ✅ 方便 AI 生成结构化流程图
  - ❌ JSON 体积随节点数增长，但单次测试节点数 < 200，可接受

### ADR-004: WebSocket 用于实时数据推送

- **状态**: 已接受
- **日期**: 2025-01-15
- **背景**: 测试执行需要实时反馈进度和设备数据
- **决策**: WebSocket 双向通道用于执行监控和设备实时数据
- **替代方案**: SSE (Server-Sent Events) → 单向，不适合；Polling → 延迟高
- **后果**: 
  - ✅ 毫秒级实时推送
  - ✅ 双向通信（可发送停止指令）
  - ❌ 需要管理连接状态和重连逻辑

### ADR-005: 插件使用 Python importlib 动态加载

- **状态**: 已接受
- **日期**: 2025-01-15
- **背景**: 需要支持用户自定义通信协议插件
- **决策**: 基于 importlib 的动态模块加载，插件实现 CommunicationPlugin ABC
- **替代方案**: 子进程通信 → 性能差；gRPC → 过于复杂
- **后果**: 
  - ✅ 热加载/卸载，无需重启
  - ✅ 插件与主程序共享内存，性能好
  - ❌ 插件代码可访问主程序内存（信任模型，需沙箱）

---

## 6. 性能目标与优化策略

| 指标 | 目标 | 优化策略 |
|------|------|----------|
| API 响应时间 (P95) | < 200ms | 异步 I/O、数据库索引、React Query 缓存 |
| WebSocket 延迟 | < 50ms | 内存缓冲、批量推送 |
| 通信日志写入 | > 1000 条/秒 | 批量写入、WAL 模式 |
| 前端首屏加载 | < 2s | Vite 代码分割、路由懒加载、Tree Shaking |
| 流程图渲染 | 200 节点流畅 | ReactFlow 虚拟化、节点 memo 化 |
| 报告生成 (PDF) | < 5s | 异步生成、Jinja2 缓存 |
| AI 调用超时 | 30s | 可配置超时、重试机制 |

---

## 7. 安全设计（Phase 1 预留）

- **API Key 加密存储**: 使用 Python `cryptography` 库 AES 加密 AI API Key
- **插件沙箱**: 限制插件文件系统和网络访问
- **SQL 注入防护**: SQLAlchemy 参数化查询 + 自然语言查询 SQL 安全校验
- **CORS**: FastAPI CORSMiddleware，开发环境允许 localhost
- **输入验证**: Pydantic 模型严格验证所有输入
