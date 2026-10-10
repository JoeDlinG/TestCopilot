"""Plugin editor service — plugin templates + source file CRUD.

Backs the in-app **插件编辑器**:

* list / read the plugin templates shipped in ``plugins/templates/``,
* create a new plugin file from a template (placeholders filled in),
* list / read / write / delete plugin source files in ``plugins/``,
* syntax-check + class-check a plugin before installing it.

Templates live in a subdirectory so the plugin scanner (which only looks at
``plugins/*.py``) never mistakes them for real plugins.
"""
from __future__ import annotations
import ast
import logging
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.core.config import settings
from app.core.timeutils import from_timestamp, utc_now

logger = logging.getLogger(__name__)

#: Placeholder syntax used inside the template files.
PLACEHOLDER_RE = re.compile(r"\{\{\s*([A-Z_]+)\s*\}\}")

_SAFE_MODULE_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")
_SAFE_PROTOCOL_RE = re.compile(r"^[a-z0-9][a-z0-9_\-]*$")


def _backend_root() -> Path:
    return Path(__file__).resolve().parents[2]  # .../backend


def plugin_dir() -> Path:
    d = Path(settings.PLUGIN_DIR)
    return d if d.is_absolute() else _backend_root() / d


def templates_dir() -> Path:
    return plugin_dir() / "templates"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _class_name(plugin_name: str) -> str:
    """Turn a human/plugin name into a PascalCase class name."""
    parts = re.split(r"[^A-Za-z0-9]+", plugin_name or "")
    name = "".join(p.capitalize() for p in parts if p)
    if not name:
        name = "Custom"
    if not name.endswith("Plugin"):
        name += "Plugin"
    return name


def _module_name(protocol: str) -> str:
    base = re.sub(r"[^a-z0-9_]", "_", (protocol or "custom").lower()).strip("_")
    return f"{base or 'custom'}_plugin"


class PluginEditorService:
    # ------------------------------------------------------------------ #
    # Templates
    # ------------------------------------------------------------------ #
    def list_templates(self) -> List[Dict[str, Any]]:
        """Return metadata for every shipped plugin template."""
        tdir = templates_dir()
        templates: List[Dict[str, Any]] = []
        if not tdir.is_dir():
            return templates
        for filename in sorted(os.listdir(tdir)):
            if not filename.endswith(".py") or filename.startswith("_"):
                continue
            path = tdir / filename
            try:
                text = _read(path)
            except OSError:
                continue
            templates.append({
                "key": filename[:-3],
                "name": self._template_meta(text, "NAME") or filename[:-3],
                "plugin_type": self._template_meta(text, "TYPE") or "protocol",
                "description": self._template_meta(text, "DESCRIPTION") or "",
                "file": str(path),
                "lines": len(text.splitlines()),
            })
        # Built-in templates are listed first, user templates after
        return sorted(templates, key=lambda t: (t["plugin_type"] != "protocol", t["key"]))

    @staticmethod
    def _template_meta(text: str, key: str) -> Optional[str]:
        m = re.search(rf"^#\s*TEMPLATE_{key}:\s*(.+)$", text, re.MULTILINE)
        return m.group(1).strip() if m else None

    def get_template(self, key: str) -> Optional[Dict[str, Any]]:
        for tpl in self.list_templates():
            if tpl["key"] == key:
                return {**tpl, "content": _read(Path(tpl["file"]))}
        return None

    def render_template(
        self,
        key: str,
        plugin_name: str,
        protocol_name: str,
        version: str = "1.0.0",
        description: str = "",
        author: str = "",
    ) -> str:
        """Fill a template's placeholders for a new plugin."""
        tpl = self.get_template(key)
        if not tpl:
            raise ValueError(f"模板不存在: {key}")
        values = {
            "PLUGIN_NAME": plugin_name or protocol_name,
            "CLASS_NAME": _class_name(plugin_name or protocol_name),
            "PROTOCOL_NAME": (protocol_name or "custom").lower(),
            "VERSION": version or "1.0.0",
            "DESCRIPTION": description or f"{plugin_name} 插件",
            "AUTHOR": author or "AITestLab",
            "DATE": utc_now().strftime("%Y-%m-%d"),
            "MODULE_NAME": _module_name(protocol_name),
        }
        return PLACEHOLDER_RE.sub(
            lambda m: values.get(m.group(1), m.group(0)), tpl["content"]
        )

    # ------------------------------------------------------------------ #
    # Plugin source files
    # ------------------------------------------------------------------ #
    def list_files(self) -> List[Dict[str, Any]]:
        """List editable ``plugins/*.py`` files."""
        pdir = plugin_dir()
        files: List[Dict[str, Any]] = []
        if not pdir.is_dir():
            return files
        for filename in sorted(os.listdir(pdir)):
            if not filename.endswith(".py") or filename.startswith("_"):
                continue
            path = pdir / filename
            if not path.is_file():
                continue
            try:
                stat = path.stat()
                text = _read(path)
            except OSError:
                continue
            files.append({
                "module_name": filename[:-3],
                "file_name": filename,
                "file_path": str(path),
                "size": stat.st_size,
                "updated_at": from_timestamp(stat.st_mtime).isoformat(),
                "classes": self._plugin_classes(text),
            })
        return files

    @staticmethod
    def _plugin_classes(text: str) -> List[str]:
        try:
            tree = ast.parse(text)
        except SyntaxError:
            return []
        names = []
        for node in tree.body:
            if not isinstance(node, ast.ClassDef):
                continue
            for base in node.bases:
                base_name = base.id if isinstance(base, ast.Name) else getattr(
                    getattr(base, "attr", None), "__str__", lambda: ""
                )()
                if base_name in ("BaseProtocolPlugin", "BaseDevicePlugin"):
                    names.append(node.name)
                    break
        return names

    def read_file(self, module_name: str) -> Optional[Dict[str, Any]]:
        path = plugin_dir() / f"{module_name}.py"
        if not path.is_file():
            return None
        return {
            "module_name": module_name,
            "file_name": path.name,
            "file_path": str(path),
            "content": _read(path),
        }

    def write_file(self, module_name: str, content: str) -> Dict[str, Any]:
        if not _SAFE_MODULE_RE.match(module_name or ""):
            raise ValueError(f"非法插件文件名 '{module_name}'")
        path = plugin_dir() / f"{module_name}.py"
        if not str(path).startswith(str(plugin_dir())):
            raise ValueError("插件路径越界")
        _write(path, content)
        return {
            "module_name": module_name,
            "file_name": path.name,
            "file_path": str(path),
            "classes": self._plugin_classes(content),
        }

    def create_file(
        self,
        plugin_name: str,
        protocol_name: str,
        template_key: str = "protocol_plugin",
        version: str = "1.0.0",
        description: str = "",
        author: str = "",
        module_name: Optional[str] = None,
        overwrite: bool = False,
    ) -> Dict[str, Any]:
        """Create a new plugin file from a template (with a runnable example)."""
        protocol = (protocol_name or "").strip().lower()
        if not _SAFE_PROTOCOL_RE.match(protocol):
            raise ValueError(
                "协议名只能包含小写字母、数字、下划线与连字符，且以字母/数字开头"
            )
        module = (module_name or "").strip() or _module_name(protocol)
        if not _SAFE_MODULE_RE.match(module):
            raise ValueError(f"非法插件文件名 '{module}'")

        path = plugin_dir() / f"{module}.py"
        if path.is_file() and not overwrite:
            raise ValueError(f"插件文件已存在: {path.name}（勾选覆盖后再试）")

        content = self.render_template(
            template_key,
            plugin_name=plugin_name or protocol,
            protocol_name=protocol,
            version=version,
            description=description,
            author=author,
        )
        _write(path, content)
        return {
            "module_name": module,
            "file_name": path.name,
            "file_path": str(path),
            "content": content,
            "classes": self._plugin_classes(content),
        }

    def delete_file(self, module_name: str) -> bool:
        path = plugin_dir() / f"{module_name}.py"
        if not path.is_file():
            return False
        path.unlink()
        return True

    # ------------------------------------------------------------------ #
    # Validation
    # ------------------------------------------------------------------ #
    def validate(self, module_name: str, content: Optional[str] = None) -> Dict[str, Any]:
        """Syntax-check a plugin source and report the plugin classes found."""
        if content is None:
            data = self.read_file(module_name)
            if not data:
                raise ValueError(f"插件文件不存在: {module_name}")
            content = data["content"]
        try:
            compile(content, f"{module_name}.py", "exec")
        except SyntaxError as e:
            return {
                "ok": False,
                "module_name": module_name,
                "error": f"{e.msg} (行 {e.lineno})",
                "classes": [],
            }
        classes = self._plugin_classes(content)
        return {
            "ok": True,
            "module_name": module_name,
            "classes": classes,
            "error": None if classes else
            "语法通过，但未找到继承 BaseProtocolPlugin 的插件类",
        }


plugin_editor_service = PluginEditorService()
