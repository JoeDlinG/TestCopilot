# AITestLab 数据库详细设计文档

## 1. 概述

- **数据库**: SQLite 3
- **ORM**: SQLAlchemy 2.0+
- **迁移工具**: Alembic
- **字符集**: UTF-8
- **ID 策略**: UUID4（短格式，前缀标识实体类型）

---

## 2. 表关系图（文字描述）

```
┌──────────────┐       ┌──────────────────┐
│   devices    │──1:N──│ communication_logs│
└──────┬───────┘       └──────────────────┘
       │
       │ 1:N
       ▼
┌──────────────┐       ┌──────────────────┐
│  test_cases  │──1:1──│   test_flows     │
└──────┬───────┘       │  (nodes JSON)    │
       │               └──────────────────┘
       │ 1:N
       ▼
┌──────────────────┐
│ test_executions  │──1:N──┐
└────────┬─────────┘       │
         │                 ▼
         │ 1:N    ┌──────────────────┐
         └───────▶│test_step_results │
                  └──────────────────┘

┌──────────────┐
│  ai_models   │ (独立表)
└──────────────┘

┌──────────────┐
│   plugins    │ (独立表)
└──────────────┘

┌──────────────┐       ┌──────────────────┐
│test_reports  │──N:1──│ report_templates │
└──────┬───────┘       └──────────────────┘
       │
       │ N:1
       ▼
┌──────────────────┐
│ test_executions  │
└──────────────────┘
```

---

## 3. 完整表结构

### 3.1 devices - 设备表

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | VARCHAR(20) | PK, NOT NULL | 设备 ID，格式 `dev_xxxxxxxx` |
| name | VARCHAR(200) | NOT NULL | 设备名称 |
| type | VARCHAR(50) | NOT NULL, INDEX | 设备类型枚举 |
| protocol | VARCHAR(20) | NOT NULL | 通信协议枚举 |
| connection_type | VARCHAR(20) | NOT NULL | 连接方式枚举 |
| visa_address | VARCHAR(500) | NULLABLE | VISA 地址 |
| can_channel | VARCHAR(100) | NULLABLE | CAN 通道配置 |
| serial_port | VARCHAR(200) | NULLABLE | 串口路径 |
| ip_address | VARCHAR(45) | NULLABLE | IP 地址 |
| port | INTEGER | NULLABLE | 端口号 |
| status | VARCHAR(20) | NOT NULL, DEFAULT 'disconnected', INDEX | 设备状态 |
| config | TEXT | NULLABLE | JSON 格式配置参数 |
| metadata | TEXT | NULLABLE | JSON 格式元数据（厂商、型号等） |
| connected_at | DATETIME | NULLABLE | 连接时间 |
| disconnected_at | DATETIME | NULLABLE | 断开时间 |
| last_seen | DATETIME | NULLABLE | 最后活跃时间 |
| created_at | DATETIME | NOT NULL, DEFAULT CURRENT_TIMESTAMP | 创建时间 |
| updated_at | DATETIME | NOT NULL, DEFAULT CURRENT_TIMESTAMP | 更新时间 |

**索引:**
- `idx_devices_status` ON (status)
- `idx_devices_type` ON (type)
- `idx_devices_protocol` ON (protocol)

**config JSON 结构示例:**
```json
{
  "timeout": 5000,
  "baud_rate": 115200,
  "data_bits": 8,
  "stop_bits": 1,
  "parity": "none",
  "can_bitrate": 500000,
  "termination_char": "\n"
}
```

**metadata JSON 结构示例:**
```json
{
  "manufacturer": "Keysight Technologies",
  "model": "DSO-X 3034A",
  "serial_number": "MY59012345",
  "firmware_version": "07.40.2021031101"
}
```

---

### 3.2 test_cases - 测试用例表

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | VARCHAR(20) | PK, NOT NULL | 用例 ID，格式 `tc_xxxxxxxx` |
| name | VARCHAR(300) | NOT NULL | 用例名称 |
| description | TEXT | NULLABLE | 用例描述 |
| requirement_raw | TEXT | NULLABLE | 原始需求文本 |
| status | VARCHAR(20) | NOT NULL, DEFAULT 'draft', INDEX | 状态枚举 |
| flow_id | VARCHAR(20) | FK → test_flows.id, NULLABLE | 关联流程图 |
| ai_model_id | VARCHAR(20) | FK → ai_models.id, NULLABLE | 生成使用的 AI 模型 |
| tags | TEXT | NULLABLE | JSON 数组，标签 |
| created_at | DATETIME | NOT NULL, DEFAULT CURRENT_TIMESTAMP | 创建时间 |
| updated_at | DATETIME | NOT NULL, DEFAULT CURRENT_TIMESTAMP | 更新时间 |

**索引:**
- `idx_test_cases_status` ON (status)
- `idx_test_cases_flow_id` ON (flow_id)

---

### 3.3 test_flows - 测试流程图表

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | VARCHAR(20) | PK, NOT NULL | 流程 ID，格式 `flow_xxxxxxxx` |
| testcase_id | VARCHAR(20) | FK → test_cases.id, UNIQUE, NOT NULL | 关联用例 |
| nodes | TEXT | NOT NULL, DEFAULT '[]' | JSON，节点数组 |
| edges | TEXT | NOT NULL, DEFAULT '[]' | JSON，边数组 |
| viewport | TEXT | NULLABLE | JSON，画布视口状态 |
| created_at | DATETIME | NOT NULL, DEFAULT CURRENT_TIMESTAMP | 创建时间 |
| updated_at | DATETIME | NOT NULL, DEFAULT CURRENT_TIMESTAMP | 更新时间 |

**nodes JSON 结构:**
```json
[
  {
    "id": "node_1",
    "type": "start",
    "label": "开始",
    "position": { "x": 100, "y": 50 },
    "config": {}
  },
  {
    "id": "node_2",
    "type": "test_step",
    "label": "设置电源输出 12V",
    "position": { "x": 100, "y": 150 },
    "config": {
      "device_id": "dev_001",
      "command": "VOLT 12",
      "expected": "12.0 ± 0.1V",
      "timeout": 5000,
      "retry_count": 0
    }
  },
  {
    "id": "node_3",
    "type": "condition",
    "label": "电压是否正常？",
    "position": { "x": 100, "y": 300 },
    "config": {
      "expression": "voltage > 4.75 and voltage < 5.25",
      "true_label": "正常",
      "false_label": "异常"
    }
  }
]
```

**edges JSON 结构:**
```json
[
  { "id": "e1", "source": "node_1", "target": "node_2", "label": "" },
  { "id": "e2", "source": "node_2", "target": "node_3", "label": "" },
  { "id": "e3", "source": "node_3", "target": "node_4", "label": "正常" },
  { "id": "e4", "source": "node_3", "target": "node_5", "label": "异常" }
]
```

---

### 3.4 test_executions - 测试执行记录表

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | VARCHAR(20) | PK, NOT NULL | 执行 ID，格式 `exec_xxxxxxxx` |
| testcase_id | VARCHAR(20) | FK → test_cases.id, NOT NULL, INDEX | 关联测试用例 |
| status | VARCHAR(20) | NOT NULL, DEFAULT 'pending', INDEX | 执行状态枚举 |
| result | VARCHAR(20) | NULLABLE | 执行结果枚举 |
| options | TEXT | NULLABLE | JSON，执行选项 |
| total_steps | INTEGER | NOT NULL, DEFAULT 0 | 总步骤数 |
| passed_steps | INTEGER | NOT NULL, DEFAULT 0 | 通过步骤数 |
| failed_steps | INTEGER | NOT NULL, DEFAULT 0 | 失败步骤数 |
| error_message | TEXT | NULLABLE | 错误信息 |
| started_at | DATETIME | NULLABLE | 开始时间 |
| completed_at | DATETIME | NULLABLE | 完成时间 |
| duration_ms | INTEGER | NULLABLE | 执行耗时（毫秒） |
| created_at | DATETIME | NOT NULL, DEFAULT CURRENT_TIMESTAMP | 创建时间 |

**索引:**
- `idx_executions_testcase_id` ON (testcase_id)
- `idx_executions_status` ON (status)
- `idx_executions_result` ON (result)
- `idx_executions_created_at` ON (created_at)

**options JSON 结构:**
```json
{
  "stop_on_error": true,
  "timeout_per_step": 30000,
  "parallel_devices": false
}
```

---

### 3.5 test_step_results - 步骤执行结果表

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | VARCHAR(20) | PK, NOT NULL | 结果 ID，格式 `step_xxxxxxxx` |
| execution_id | VARCHAR(20) | FK → test_executions.id, NOT NULL, INDEX | 关联执行 |
| step_index | INTEGER | NOT NULL | 步骤序号 |
| node_id | VARCHAR(50) | NOT NULL | 流程图节点 ID |
| node_type | VARCHAR(20) | NOT NULL | 节点类型 |
| label | VARCHAR(300) | NOT NULL | 步骤标签 |
| status | VARCHAR(20) | NOT NULL | 步骤状态：passed/failed/error/skipped |
| command | TEXT | NULLABLE | 发送的指令 |
| expected | TEXT | NULLABLE | 预期结果 |
| actual | TEXT | NULLABLE | 实际结果 |
| error_message | TEXT | NULLABLE | 错误信息 |
| started_at | DATETIME | NULLABLE | 开始时间 |
| completed_at | DATETIME | NULLABLE | 完成时间 |
| duration_ms | INTEGER | NULLABLE | 耗时 |

**索引:**
- `idx_step_results_execution_id` ON (execution_id)
- `idx_step_results_execution_step` ON (execution_id, step_index)

---

### 3.6 communication_logs - 通信日志表

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | VARCHAR(20) | PK, NOT NULL | 日志 ID，格式 `log_xxxxxxxx` |
| timestamp | DATETIME | NOT NULL, INDEX | 时间戳（高精度） |
| device_id | VARCHAR(20) | FK → devices.id, NOT NULL, INDEX | 关联设备 |
| execution_id | VARCHAR(20) | FK → test_executions.id, NULLABLE, INDEX | 关联执行 |
| step_result_id | VARCHAR(20) | FK → test_step_results.id, NULLABLE | 关联步骤结果 |
| direction | VARCHAR(10) | NOT NULL | sent / received |
| protocol | VARCHAR(20) | NOT NULL | 通信协议 |
| raw_data | TEXT | NOT NULL | 原始数据（文本） |
| raw_data_hex | TEXT | NULLABLE | 原始数据（十六进制） |
| raw_data_size | INTEGER | NULLABLE | 数据大小（字节） |
| status | VARCHAR(20) | NOT NULL, DEFAULT 'success' | success / error / timeout |
| error_message | TEXT | NULLABLE | 错误信息 |
| duration_ms | INTEGER | NULLABLE | 通信耗时（毫秒） |
| response_log_id | VARCHAR(20) | FK → communication_logs.id, NULLABLE | 关联的响应日志 |
| metadata | TEXT | NULLABLE | JSON，额外元数据 |

**索引:**
- `idx_logs_timestamp` ON (timestamp)
- `idx_logs_device_id` ON (device_id)
- `idx_logs_execution_id` ON (execution_id)
- `idx_logs_device_timestamp` ON (device_id, timestamp)
- `idx_logs_direction` ON (direction)

**metadata JSON 结构:**
```json
{
  "interface": "USB",
  "visa_session": "USB0::...::INSTR",
  "retry_count": 0
}
```

---

### 3.7 ai_models - AI 模型配置表

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | VARCHAR(20) | PK, NOT NULL | 模型配置 ID，格式 `model_xxxxxxxx` |
| name | VARCHAR(200) | NOT NULL | 配置名称（用户自定义） |
| provider | VARCHAR(50) | NOT NULL | 提供商枚举 |
| model_name | VARCHAR(200) | NOT NULL | 模型名称（如 gpt-4o, llama3:8b） |
| api_key_encrypted | TEXT | NULLABLE | 加密存储的 API Key |
| base_url | VARCHAR(500) | NULLABLE | API 端点 URL |
| parameters | TEXT | NULLABLE | JSON，默认参数 |
| is_default | BOOLEAN | NOT NULL, DEFAULT FALSE | 是否为默认模型 |
| status | VARCHAR(20) | NOT NULL, DEFAULT 'active' | active / disabled / error |
| last_tested_at | DATETIME | NULLABLE | 最后测试时间 |
| created_at | DATETIME | NOT NULL, DEFAULT CURRENT_TIMESTAMP | 创建时间 |
| updated_at | DATETIME | NOT NULL, DEFAULT CURRENT_TIMESTAMP | 更新时间 |

**索引:**
- `idx_ai_models_provider` ON (provider)
- `idx_ai_models_is_default` ON (is_default)

**provider 枚举值:**
`openai`, `anthropic`, `ollama`, `localai`, `vllm`, `hunyuan`, `qwen`, `ernie`, `custom`

**parameters JSON 结构:**
```json
{
  "temperature": 0.7,
  "max_tokens": 4096,
  "top_p": 1.0,
  "frequency_penalty": 0,
  "presence_penalty": 0
}
```

---

### 3.8 plugins - 插件表

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | VARCHAR(20) | PK, NOT NULL | 插件 ID，格式 `plg_xxxxxxxx` |
| name | VARCHAR(200) | NOT NULL, UNIQUE | 插件名称 |
| version | VARCHAR(50) | NOT NULL | 版本号 |
| description | TEXT | NULLABLE | 描述 |
| author | VARCHAR(200) | NULLABLE | 作者 |
| protocol_type | VARCHAR(50) | NOT NULL | 协议类型 |
| status | VARCHAR(20) | NOT NULL, DEFAULT 'installed' | 状态枚举 |
| file_path | VARCHAR(500) | NOT NULL | 插件文件路径 |
| module_name | VARCHAR(200) | NOT NULL | Python 模块名 |
| class_name | VARCHAR(200) | NOT NULL | 插件类名 |
| config_schema | TEXT | NULLABLE | JSON Schema，配置项定义 |
| config | TEXT | NULLABLE | JSON，当前配置值 |
| entry_point | VARCHAR(200) | NULLABLE | setuptools entry_point |
| error_message | TEXT | NULLABLE | 加载错误信息 |
| installed_at | DATETIME | NOT NULL, DEFAULT CURRENT_TIMESTAMP | 安装时间 |
| enabled_at | DATETIME | NULLABLE | 启用时间 |
| disabled_at | DATETIME | NULLABLE | 禁用时间 |
| updated_at | DATETIME | NOT NULL, DEFAULT CURRENT_TIMESTAMP | 更新时间 |

**索引:**
- `idx_plugins_name` ON (name) UNIQUE
- `idx_plugins_status` ON (status)
- `idx_plugins_protocol_type` ON (protocol_type)

---

### 3.9 test_reports - 测试报告表

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | VARCHAR(20) | PK, NOT NULL | 报告 ID，格式 `rpt_xxxxxxxx` |
| title | VARCHAR(300) | NOT NULL | 报告标题 |
| execution_id | VARCHAR(20) | FK → test_executions.id, NOT NULL, INDEX | 关联执行 |
| template_id | VARCHAR(20) | FK → report_templates.id, NULLABLE | 关联模板 |
| format | VARCHAR(10) | NOT NULL | 格式：pdf / html / docx |
| status | VARCHAR(20) | NOT NULL, DEFAULT 'generating' | generating / generated / failed |
| file_path | VARCHAR(500) | NULLABLE | 生成的文件路径 |
| file_size | INTEGER | NULLABLE | 文件大小（字节） |
| fields | TEXT | NULLABLE | JSON，用户填写的字段值 |
| error_message | TEXT | NULLABLE | 生成失败错误信息 |
| created_at | DATETIME | NOT NULL, DEFAULT CURRENT_TIMESTAMP | 创建时间 |
| generated_at | DATETIME | NULLABLE | 生成完成时间 |

**索引:**
- `idx_reports_execution_id` ON (execution_id)

**fields JSON 结构:**
```json
{
  "title": "DCDC 转换器测试报告",
  "author": "张三",
  "conclusion": "所有测试项通过",
  "custom_fields": {
    "environment_temp": "25°C",
    "humidity": "45%"
  }
}
```

---

### 3.10 report_templates - 报告模板表

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | VARCHAR(20) | PK, NOT NULL | 模板 ID，格式 `tpl_xxxxxxxx` |
| name | VARCHAR(200) | NOT NULL | 模板名称 |
| description | TEXT | NULLABLE | 模板描述 |
| format | VARCHAR(10) | NOT NULL | 默认格式：pdf / html / docx |
| content | TEXT | NOT NULL | Jinja2 模板内容 |
| fields_schema | TEXT | NULLABLE | JSON Schema，定义模板字段 |
| is_default | BOOLEAN | NOT NULL, DEFAULT FALSE | 是否默认模板 |
| created_at | DATETIME | NOT NULL, DEFAULT CURRENT_TIMESTAMP | 创建时间 |
| updated_at | DATETIME | NOT NULL, DEFAULT CURRENT_TIMESTAMP | 更新时间 |

---

### 3.11 系统配置表（预留）

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| key | VARCHAR(200) | PK, NOT NULL | 配置键 |
| value | TEXT | NOT NULL | 配置值（JSON） |
| description | TEXT | NULLABLE | 配置说明 |
| updated_at | DATETIME | NOT NULL, DEFAULT CURRENT_TIMESTAMP | 更新时间 |

---

## 4. SQLAlchemy 模型定义示例

```python
# models/device.py
from sqlalchemy import Column, String, Integer, DateTime, Text, func
from app.core.database import Base

class Device(Base):
    __tablename__ = "devices"

    id = Column(String(20), primary_key=True)
    name = Column(String(200), nullable=False)
    type = Column(String(50), nullable=False, index=True)
    protocol = Column(String(20), nullable=False)
    connection_type = Column(String(20), nullable=False)
    visa_address = Column(String(500), nullable=True)
    can_channel = Column(String(100), nullable=True)
    serial_port = Column(String(200), nullable=True)
    ip_address = Column(String(45), nullable=True)
    port = Column(Integer, nullable=True)
    status = Column(String(20), nullable=False, default="disconnected", index=True)
    config = Column(Text, nullable=True)      # JSON
    metadata = Column(Text, nullable=True)    # JSON
    connected_at = Column(DateTime, nullable=True)
    disconnected_at = Column(DateTime, nullable=True)
    last_seen = Column(DateTime, nullable=True)
    created_at = Column(DateTime, nullable=False, server_default=func.now())
    updated_at = Column(DateTime, nullable=False, server_default=func.now(), onupdate=func.now())
```

---

## 5. 迁移策略

### 5.1 迁移工具

使用 **Alembic** 进行数据库迁移管理：

```
backend/
├── alembic/
│   ├── versions/          # 迁移脚本
│   ├── env.py
│   └── alembic.ini
```

### 5.2 迁移原则

1. **每个版本独立**：每次表结构变更生成一个迁移文件
2. **向前兼容**：新增字段设默认值，不删除字段（标记 deprecated）
3. **可回滚**：每个 upgrade() 对应一个 downgrade()
4. **数据迁移优先**：先迁移结构，再迁移数据
5. **测试验证**：每次迁移在 CI 中验证 upgrade → downgrade → upgrade 循环

### 5.3 初始化迁移

```bash
# 初始化 Alembic
cd backend
alembic init alembic

# 生成初始迁移（自动检测模型）
alembic revision --autogenerate -m "initial_schema"

# 应用迁移
alembic upgrade head

# 回滚
alembic downgrade -1
```

### 5.4 Phase 对应的迁移

| Phase | 涉及表 |
|-------|--------|
| Phase 1 | 全部表初始化 |
| Phase 2 | devices, communication_logs |
| Phase 3 | ai_models, test_cases, test_flows |
| Phase 4 | test_executions, test_step_results |
| Phase 5 | test_reports, report_templates |
| Phase 6 | plugins |

### 5.5 从 SQLite 迁移到 PostgreSQL 的预留设计

- 所有 ID 使用 VARCHAR（非自增 INTEGER），方便跨数据库迁移
- JSON 字段使用 TEXT 存储，兼容 SQLite（无原生 JSON 类型）
- 时间字段使用 DATETIME，避免依赖数据库特定函数
- 避免使用 SQLite 特有的 `AUTOINCREMENT`，使用应用层 UUID 生成
- 外键显式定义，便于迁移工具识别

---

## 6. 数据访问层设计

### 6.1 Repository 模式

```python
# repositories/base.py
from typing import Generic, TypeVar, Type, Optional, List
from sqlalchemy.orm import Session

T = TypeVar("T")

class BaseRepository(Generic[T]):
    def __init__(self, db: Session, model: Type[T]):
        self.db = db
        self.model = model

    def get_by_id(self, id: str) -> Optional[T]:
        return self.db.query(self.model).filter(self.model.id == id).first()

    def list(self, skip: int = 0, limit: int = 20) -> List[T]:
        return self.db.query(self.model).offset(skip).limit(limit).all()

    def create(self, entity: T) -> T:
        self.db.add(entity)
        self.db.commit()
        self.db.refresh(entity)
        return entity

    def update(self, entity: T) -> T:
        self.db.commit()
        self.db.refresh(entity)
        return entity

    def delete(self, entity: T) -> None:
        self.db.delete(entity)
        self.db.commit()
```

### 6.2 事务管理

使用 FastAPI 依赖注入管理会话生命周期：

```python
# core/database.py
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session

engine = create_engine("sqlite:///./aitestlab.db", echo=False)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def get_db() -> Session:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
```
