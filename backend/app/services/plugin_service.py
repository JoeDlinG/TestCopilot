"""Plugin management service — dynamic loading via importlib."""
from __future__ import annotations
import importlib
import importlib.util
import json
import logging
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.models import Plugin, PluginStatus
from app.core.config import settings

logger = logging.getLogger(__name__)


class BaseProtocolPlugin:
    """Base class for all custom protocol plugins.

    A plugin wraps a physical transport (serial/USB/Ethernet/...) and exposes a
    high-level, device-specific command interface. It mirrors the
    ``CommunicationInterface`` contract (connect/disconnect/send/receive) so the
    device service can use a plugin instance as a drop-in communication backend
    for ``custom`` protocol devices.

    Subclasses MUST implement ``connect``, ``disconnect`` and ``send``.
    They SHOULD set ``plugin_name``, ``protocol_name`` and ``version`` class
    attributes, and may override ``get_config_schema``, ``get_device_template``
    and ``get_commands``.
    """

    #: Human readable plugin name (shown in the UI).
    plugin_name: str = "Base Protocol"
    #: Unique protocol identifier. Devices using this plugin set their
    #: ``protocol`` field to this value.
    protocol_name: str = "custom"
    #: Plugin version string.
    version: str = "0.1.0"

    async def connect(self, config: dict) -> bool:
        """Open the underlying transport using the provided config dict."""
        raise NotImplementedError("Plugin must implement connect()")

    async def disconnect(self) -> bool:
        """Close the underlying transport."""
        raise NotImplementedError("Plugin must implement disconnect()")

    async def send(self, data: any) -> any:
        """Send a command and return the parsed result.

        ``data`` may be:
          * a raw protocol string (e.g. ``"@11_SYSID=;"``) — forwarded as-is, or
          * a dict ``{"command": "SYSID", "parameters": [...]}`` — formatted by
            the plugin.
        """
        raise NotImplementedError("Plugin must implement send()")

    async def receive(self) -> any:
        """Receive unsolicited data from the device (if supported)."""
        raise NotImplementedError("Plugin must implement receive()")

    def get_config_schema(self) -> dict:
        """Return a JSON schema describing the connection config for the UI."""
        return {"type": "object", "properties": {}}

    def get_status(self) -> dict:
        """Return a status dict for the UI."""
        return {
            "name": self.plugin_name,
            "protocol": self.protocol_name,
            "version": self.version,
        }

    def get_device_template(self) -> dict:
        """Return a template dict used to create a Device from this plugin.

        Keys map directly to ``DeviceCreate`` (name, type, protocol,
        connection_type, config, ...). Return ``{}`` if the plugin does not
        provide a device template.
        """
        return {}

    def get_commands(self) -> list:
        """Return a list of command descriptors for UI help/auto-completion.

        Each descriptor: ``{"name", "syntax", "description", "parameters": [...]}``
        """
        return []


class PluginService:
    """Service for managing protocol plugins."""

    async def install_plugin(self, db: AsyncSession, data: dict) -> Plugin:
        config_schema = data.pop("config_schema", None)
        config = data.pop("config", None)

        plugin = Plugin(**data)
        if config_schema:
            plugin.config_schema = json.dumps(config_schema, ensure_ascii=False)
        if config:
            plugin.config = json.dumps(config, ensure_ascii=False)

        db.add(plugin)
        await db.commit()
        await db.refresh(plugin)

        # Try to load the plugin (validates file path AND class resolution)
        try:
            await self.load_plugin_class(plugin)
        except Exception as e:
            logger.warning(f"Plugin {plugin.name} installed but failed to load: {e}")
            plugin.error_message = str(e)
            await db.commit()

        return plugin

    async def list_plugins(self, db: AsyncSession) -> List[Plugin]:
        result = await db.execute(
            select(Plugin).order_by(Plugin.installed_at.desc())
        )
        return result.scalars().all()

    async def get_plugin(self, db: AsyncSession, plugin_id: str) -> Optional[Plugin]:
        result = await db.execute(
            select(Plugin).where(Plugin.id == plugin_id)
        )
        return result.scalar_one_or_none()

    async def enable_plugin(self, db: AsyncSession, plugin_id: str) -> Plugin:
        plugin = await self.get_plugin(db, plugin_id)
        if not plugin:
            raise ValueError(f"Plugin {plugin_id} not found")

        try:
            await self.load_plugin_class(plugin)
            plugin.status = PluginStatus.ENABLED.value
            plugin.enabled_at = datetime.utcnow()
            plugin.error_message = None
            await db.commit()
            await db.refresh(plugin)
            return plugin
        except Exception as e:
            plugin.status = PluginStatus.ERROR.value
            plugin.error_message = str(e)
            await db.commit()
            raise

    async def disable_plugin(self, db: AsyncSession, plugin_id: str) -> Plugin:
        plugin = await self.get_plugin(db, plugin_id)
        if not plugin:
            raise ValueError(f"Plugin {plugin_id} not found")

        plugin.status = PluginStatus.DISABLED.value
        plugin.disabled_at = datetime.utcnow()
        await db.commit()
        await db.refresh(plugin)
        return plugin

    async def uninstall_plugin(self, db: AsyncSession, plugin_id: str) -> bool:
        plugin = await self.get_plugin(db, plugin_id)
        if not plugin:
            return False
        await db.delete(plugin)
        await db.commit()
        return True

    # ------------------------------------------------------------------ #
    # Robust plugin file / module / class resolution
    # ------------------------------------------------------------------ #
    def _resolve_plugin_file(self, plugin: Plugin) -> str:
        """Resolve the plugin source file to an absolute existing path.

        The DB may store relative paths (e.g. ``./plugins/foo.py``) that break
        when the process CWD differs. Try, in order:
          1. the stored path as-is (absolute or CWD-relative),
          2. the stored path relative to the backend root,
          3. ``PLUGIN_DIR/<basename>``,
          4. ``PLUGIN_DIR/<module_name>.py``.
        """
        backend_root = Path(__file__).resolve().parents[2]  # .../backend
        plugin_dir = Path(settings.PLUGIN_DIR)
        if not plugin_dir.is_absolute():
            plugin_dir = backend_root / plugin_dir

        candidates = []
        if plugin.file_path:
            candidates.append(Path(plugin.file_path))
            candidates.append(backend_root / plugin.file_path)
            candidates.append(plugin_dir / Path(plugin.file_path).name)
        if plugin.module_name:
            candidates.append(plugin_dir / f"{plugin.module_name}.py")

        for cand in candidates:
            try:
                if cand.is_file():
                    return str(cand.resolve())
            except OSError:
                continue

        raise FileNotFoundError(
            f"Plugin file not found: {plugin.file_path} "
            f"(also tried under {plugin_dir})"
        )

    def _exec_module(self, module_name: str, file_path: str) -> Any:
        """Import a python file as a module (backend root on sys.path)."""
        backend_root = str(Path(__file__).resolve().parents[2])
        if backend_root not in sys.path:
            # Plugins import ``app.services.plugin_service`` — make sure the
            # backend package is importable regardless of process CWD.
            sys.path.insert(0, backend_root)

        spec = importlib.util.spec_from_file_location(module_name, file_path)
        if spec is None or spec.loader is None:
            raise ImportError(f"Cannot load spec for {module_name} ({file_path})")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    @staticmethod
    def _find_plugin_classes(module: Any) -> List[type]:
        """Return all BaseProtocolPlugin subclasses defined in a module."""
        classes = []
        for attr_name in dir(module):
            attr = getattr(module, attr_name)
            if (
                isinstance(attr, type)
                and issubclass(attr, BaseProtocolPlugin)
                and attr is not BaseProtocolPlugin
            ):
                classes.append(attr)
        return classes

    async def _load_plugin_module(self, plugin: Plugin) -> Any:
        """Dynamically load a plugin's module via importlib (returns module)."""
        file_path = self._resolve_plugin_file(plugin)
        return self._exec_module(plugin.module_name, file_path)

    async def load_plugin_class(self, plugin: Plugin) -> type:
        """Load and return the plugin class for a Plugin DB record.

        Resolution order:
          1. exact ``class_name`` attribute on the module,
          2. case-insensitive ``class_name`` match,
          3. a unique BaseProtocolPlugin subclass in the module,
          4. a subclass whose ``protocol_name`` matches ``plugin.protocol_type``.

        This makes plugin loading resilient to minor metadata mismatches so
        no plugin fails with a bare "class not found".
        """
        module = await self._load_plugin_module(plugin)

        # 1. Exact match
        cls = getattr(module, plugin.class_name, None) if plugin.class_name else None
        if isinstance(cls, type):
            return cls

        candidates = self._find_plugin_classes(module)

        # 2. Case-insensitive match
        if plugin.class_name:
            for c in candidates:
                if c.__name__.lower() == plugin.class_name.lower():
                    return c

        # 3. Unique plugin subclass in the module
        if len(candidates) == 1:
            logger.warning(
                f"Plugin '{plugin.name}': class '{plugin.class_name}' not found, "
                f"falling back to sole plugin class '{candidates[0].__name__}'"
            )
            return candidates[0]

        # 4. Match by protocol
        for c in candidates:
            if getattr(c, "protocol_name", None) == plugin.protocol_type:
                logger.warning(
                    f"Plugin '{plugin.name}': class '{plugin.class_name}' not found, "
                    f"matched '{c.__name__}' by protocol '{plugin.protocol_type}'"
                )
                return c

        available = [c.__name__ for c in candidates]
        raise ImportError(
            f"Class '{plugin.class_name}' not found in module "
            f"'{plugin.module_name}'. Available plugin classes: {available or '(none)'}"
        )

    async def get_plugin_class_by_protocol(
        self, db: AsyncSession, protocol_name: str
    ) -> Any:
        """Find an ENABLED plugin whose class ``protocol_name`` matches.

        Returns the plugin class (not an instance) or ``None``.
        """
        plugins = await self.list_plugins(db)
        for plugin in plugins:
            if plugin.status != PluginStatus.ENABLED.value:
                continue
            try:
                cls = await self.load_plugin_class(plugin)
                if getattr(cls, "protocol_name", None) == protocol_name:
                    return cls
            except Exception as e:
                logger.warning(
                    f"Failed to inspect plugin {plugin.name} for protocol "
                    f"{protocol_name}: {e}"
                )
                continue
        return None

    def _resolved_plugin_dir(self) -> Path:
        """Absolute plugins directory (independent of process CWD)."""
        backend_root = Path(__file__).resolve().parents[2]
        plugin_dir = Path(settings.PLUGIN_DIR)
        if not plugin_dir.is_absolute():
            plugin_dir = backend_root / plugin_dir
        return plugin_dir

    async def list_discovered_plugins(self) -> List[Dict[str, Any]]:
        """Scan the plugins directory for discoverable plugins."""
        plugins = []
        plugin_dir = self._resolved_plugin_dir()
        if not plugin_dir.is_dir():
            return plugins

        for filename in sorted(os.listdir(plugin_dir)):
            if not filename.endswith(".py") or filename.startswith("_"):
                continue
            file_path = str(plugin_dir / filename)
            try:
                module = self._exec_module(filename[:-3], file_path)
                # Only real plugin classes (BaseProtocolPlugin subclasses)
                for cls in self._find_plugin_classes(module):
                    plugins.append({
                        "name": getattr(cls, "plugin_name", cls.__name__),
                        "version": getattr(
                            cls, "version",
                            getattr(cls, "plugin_version", "0.1.0"),
                        ),
                        "description": (cls.__doc__ or "").strip(),
                        "protocol_name": getattr(cls, "protocol_name", "custom"),
                        "module_name": filename[:-3],
                        "class_name": cls.__name__,
                        "file_path": file_path,
                    })
            except Exception as e:
                logger.warning(f"Failed to scan plugin {filename}: {e}")

        return plugins


    # ------------------------------------------------------------------ #
    # Plugin skills & manuals (used by the AI assistant)
    # ------------------------------------------------------------------ #
    @staticmethod
    def _parse_frontmatter(text: str) -> tuple[Dict[str, str], str]:
        """Parse a simple ``--- key: value ---`` frontmatter block."""
        meta: Dict[str, str] = {}
        body = text
        if text.startswith("---"):
            parts = text.split("---", 2)
            if len(parts) >= 3:
                for line in parts[1].strip().splitlines():
                    if ":" in line:
                        k, v = line.split(":", 1)
                        meta[k.strip().lower()] = v.strip()
                body = parts[2].lstrip("\n")
        return meta, body

    def list_plugin_skills(self) -> List[Dict[str, Any]]:
        """Discover plugin skills (``skills/*_skill.md``) and their manuals.

        Each skill markdown may carry frontmatter with ``name``, ``protocol``
        and ``keywords`` (comma separated). The manual is looked up at
        ``manuals/<protocol>.md``.
        """
        plugin_dir = self._resolved_plugin_dir()
        skills_dir = plugin_dir / "skills"
        manuals_dir = plugin_dir / "manuals"
        skills: List[Dict[str, Any]] = []
        if not skills_dir.is_dir():
            return skills

        for filename in sorted(os.listdir(skills_dir)):
            if not filename.endswith(".md"):
                continue
            path = skills_dir / filename
            try:
                text = path.read_text(encoding="utf-8")
            except OSError as e:
                logger.warning(f"Failed to read skill {filename}: {e}")
                continue
            meta, _ = self._parse_frontmatter(text)
            protocol = meta.get("protocol") or filename.replace("_skill.md", "").replace(".md", "")
            name = meta.get("name") or protocol
            keywords = [
                kw.strip().lower()
                for kw in meta.get("keywords", "").split(",")
                if kw.strip()
            ]
            manual_path = manuals_dir / f"{protocol}.md"
            skills.append({
                "protocol": protocol,
                "name": name,
                "keywords": keywords,
                "skill_file": str(path),
                "manual_file": str(manual_path) if manual_path.is_file() else None,
                "has_manual": manual_path.is_file(),
            })
        return skills

    # ------------------------------------------------------------------ #
    # Skill editing (create / update / import / delete)
    # ------------------------------------------------------------------ #
    def _skills_dir(self) -> Path:
        return self._resolved_plugin_dir() / "skills"

    @staticmethod
    def _build_frontmatter(meta: Dict[str, str]) -> str:
        """Render a ``--- key: value ---`` frontmatter block."""
        lines = ["---"]
        for key in ("name", "protocol", "keywords"):
            value = (meta.get(key) or "").strip()
            if value:
                lines.append(f"{key}: {value}")
        lines.append("---")
        return "\n".join(lines)

    def _skill_path(self, protocol: str) -> Path:
        return self._skills_dir() / f"{protocol}_skill.md"

    def save_plugin_skill(
        self,
        protocol: str,
        name: Optional[str] = None,
        keywords: Optional[List[str]] = None,
        content: str = "",
        rename_from: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Create or update a skill markdown file.

        ``content`` is the markdown body (without frontmatter). When
        ``rename_from`` is given and differs from *protocol*, the old file is
        removed so renaming in the editor does not leave a stale skill behind.
        """
        protocol = (protocol or "").strip()
        if not protocol:
            raise ValueError("protocol is required")
        if not re.fullmatch(r"[A-Za-z0-9_.\-]+", protocol):
            raise ValueError(
                f"非法 protocol '{protocol}'：仅允许字母、数字、下划线、点与连字符"
            )

        skills_dir = self._skills_dir()
        skills_dir.mkdir(parents=True, exist_ok=True)

        meta = {
            "name": (name or protocol).strip(),
            "protocol": protocol,
            "keywords": ", ".join(k.strip() for k in (keywords or []) if k and k.strip()),
        }
        body = (content or "").lstrip("\n")
        text = self._build_frontmatter(meta) + "\n\n" + body
        if not text.endswith("\n"):
            text += "\n"

        target = self._skill_path(protocol)
        if rename_from and rename_from.strip() and rename_from.strip() != protocol:
            old = self._skill_path(rename_from.strip())
            if old.is_file() and old != target:
                try:
                    old.unlink()
                except OSError as e:
                    logger.warning(f"Failed to remove old skill file {old}: {e}")

        target.write_text(text, encoding="utf-8")
        logger.info(f"Skill saved: {target}")
        return {
            "protocol": protocol,
            "name": meta["name"],
            "keywords": [k.strip() for k in meta["keywords"].split(",") if k.strip()],
            "skill_file": str(target),
        }

    def import_plugin_skill(self, filename: str, content: str) -> Dict[str, Any]:
        """Import a skill markdown file (frontmatter optional).

        The protocol is taken from the frontmatter, else derived from the file
        name (``foo_skill.md`` → ``foo``). An existing skill with the same
        protocol is overwritten.
        """
        meta, body = self._parse_frontmatter(content or "")
        base = (filename or "").strip()
        derived = base
        for suffix in ("_skill.md", ".md"):
            if derived.endswith(suffix):
                derived = derived[: -len(suffix)]
                break
        protocol = (meta.get("protocol") or "").strip() or derived
        if not protocol:
            raise ValueError("无法从文件内容或文件名推断 protocol")
        return self.save_plugin_skill(
            protocol=protocol,
            name=meta.get("name"),
            keywords=[
                k.strip() for k in (meta.get("keywords") or "").split(",") if k.strip()
            ],
            content=body,
        )

    def delete_plugin_skill(self, protocol: str) -> bool:
        path = self._skill_path(protocol)
        if not path.is_file():
            return False
        path.unlink()
        logger.info(f"Skill deleted: {path}")
        return True

    def get_plugin_skill_content(self, protocol: str) -> Optional[Dict[str, Any]]:
        """Return the skill + manual markdown for a protocol, or None."""
        for skill in self.list_plugin_skills():
            if skill["protocol"] != protocol:
                continue
            try:
                skill_text = Path(skill["skill_file"]).read_text(encoding="utf-8")
                _, skill_body = self._parse_frontmatter(skill_text)
            except OSError:
                skill_body = ""
            manual_body = ""
            if skill["manual_file"]:
                try:
                    manual_body = Path(skill["manual_file"]).read_text(encoding="utf-8")
                except OSError:
                    pass
            return {
                "protocol": protocol,
                "name": skill["name"],
                "skill": skill_body,
                "manual": manual_body,
            }
        return None

    def match_skills_for_text(self, text: str) -> List[str]:
        """Return protocols whose name/protocol/keywords appear in ``text``.

        Used by the AI assistant to auto-attach relevant device skills when
        the user mentions a device in conversation.
        """
        text_lower = (text or "").lower()
        matched: List[str] = []
        for skill in self.list_plugin_skills():
            needles = [skill["protocol"].lower(), skill["name"].lower(), *skill["keywords"]]
            if any(n and n in text_lower for n in needles):
                matched.append(skill["protocol"])
        return matched


plugin_service = PluginService()
