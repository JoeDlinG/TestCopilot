"""
TEMPLATE_NAME: 报告模板插件
TEMPLATE_TYPE: report
TEMPLATE_DESCRIPTION: 自定义测试报告的章节结构与渲染方式（Markdown / HTML）

{{PLUGIN_NAME}} —— 由 AITestLab 插件编辑器于 {{DATE}} 从「报告模板插件」模板生成。

报告生成流程：
  1. 平台把执行结果（用例、步骤、判定、解析数据）整理成 report_data 传入 render()；
  2. render() 返回渲染好的文本（Markdown / HTML）；
  3. 平台按 format 落盘（.md / .html / .docx）。

模板变量使用 Jinja2 语法：{{PLUGIN_NAME}} 之类会被替换，
运行期数据请用 {{ PLACEHOLDER }} 之外的写法（见下方 TEMPLATE_BODY 示例）。
"""

from app.services.plugin_service import BaseProtocolPlugin

# 注意：本文件里的双花括号是插件模板占位符语法，
# 生成后会被替换；下面是运行期报告正文模板，使用单花括号 Jinja2 变量。
TEMPLATE_BODY = """# {test_case_name} 测试报告

- 执行时间：{started_at}
- 用例总数：{total}　通过：{passed}　失败：{failed}
- 通过率：{pass_rate}

## 步骤明细

{steps_table}

## 结论

{conclusion}
"""


class {{CLASS_NAME}}(BaseProtocolPlugin):
    """{{DESCRIPTION}}"""

    plugin_name = "{{PLUGIN_NAME}}"
    protocol_name = "{{PROTOCOL_NAME}}"
    version = "{{VERSION}}"

    #: 报告字段定义（平台读取后用于「报告字段可配置」）
    FIELDS = [
        {"key": "test_case_name", "title": "用例名称", "required": True},
        {"key": "started_at", "title": "执行时间", "required": True},
        {"key": "total", "title": "步骤总数", "required": True},
        {"key": "passed", "title": "通过数", "required": True},
        {"key": "failed", "title": "失败数", "required": True},
        {"key": "pass_rate", "title": "通过率", "required": False},
    ]

    def __init__(self):
        self._connected = False

    # ------------------------------------------------------------------ #
    # 协议接口（报告插件不直接连接设备，实现为空操作即可）
    # ------------------------------------------------------------------ #
    async def connect(self, config: dict) -> bool:
        self._connected = True
        return True

    async def disconnect(self) -> bool:
        self._connected = False
        return True

    async def send(self, data) -> str:
        return ""

    async def receive(self) -> str:
        return ""

    # ------------------------------------------------------------------ #
    # 报告渲染
    # ------------------------------------------------------------------ #
    def get_fields(self) -> list:
        """返回报告字段定义，供前端字段选择与排序。"""
        return list(self.FIELDS)

    def render(self, report_data: dict) -> str:
        """把执行结果渲染成报告正文（Markdown / HTML）。

        report_data 至少包含：test_case_name / started_at / steps / total /
        passed / failed。缺失字段用占位符兜底，避免渲染中断。
        """
        steps = report_data.get("steps") or []
        rows = ["| 步骤 | 命令 | 实际 | 结果 |", "| --- | --- | --- | --- |"]
        for s in steps:
            rows.append(
                f"| {s.get('label', '')} | {s.get('command', '')} "
                f"| {s.get('actual', '')} | {s.get('status', '')} |"
            )
        total = int(report_data.get("total") or len(steps))
        passed = int(report_data.get("passed") or 0)
        failed = int(report_data.get("failed") or 0)
        rate = f"{(passed / total * 100):.1f}%" if total else "N/A"
        return TEMPLATE_BODY.format(
            test_case_name=report_data.get("test_case_name", "未命名用例"),
            started_at=report_data.get("started_at", ""),
            total=total,
            passed=passed,
            failed=failed,
            pass_rate=rate,
            steps_table="\n".join(rows),
            conclusion=report_data.get("conclusion")
            or ("全部通过" if failed == 0 else f"存在 {failed} 个失败步骤"),
        )

    def get_commands(self) -> list:
        return [{"name": "渲染报告", "syntax": "render(report_data)",
                 "description": "返回 Markdown 报告正文", "parameters": []}]
