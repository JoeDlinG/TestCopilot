"""Plugin management service — dynamic loading via importlib."""
from __future__ import annotations
import importlib
import json
import logging
import os
from datetime import datetime
from typing import Optional, List, Dict, Any

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.models import Plugin, PluginStatus
from app.core.config import settings

logger = logging.getLogger(__name__)


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

        # Try to load the plugin
        try:
            await self._load_plugin_module(plugin)
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
            await self._load_plugin_module(plugin)
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

    async def _load_plugin_module(self, plugin: Plugin) -> Any:
        """Dynamically load a plugin module via importlib."""
        if not os.path.exists(plugin.file_path):
            raise FileNotFoundError(f"Plugin file not found: {plugin.file_path}")

        spec = importlib.util.spec_from_file_location(
            plugin.module_name, plugin.file_path
        )
        if spec is None or spec.loader is None:
            raise ImportError(f"Cannot load spec for {plugin.module_name}")

        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        # Verify the plugin class exists
        plugin_class = getattr(module, plugin.class_name, None)
        if plugin_class is None:
            raise ImportError(
                f"Class '{plugin.class_name}' not found in {plugin.module_name}"
            )

        return plugin_class

    async def list_discovered_plugins(self) -> List[Dict[str, Any]]:
        """Scan the plugins directory for discoverable plugins."""
        plugins = []
        plugin_dir = settings.PLUGIN_DIR
        if not os.path.isdir(plugin_dir):
            return plugins

        for filename in os.listdir(plugin_dir):
            if filename.endswith(".py") and not filename.startswith("_"):
                file_path = os.path.join(plugin_dir, filename)
                try:
                    spec = importlib.util.spec_from_file_location(
                        filename[:-3], file_path
                    )
                    if spec and spec.loader:
                        module = importlib.util.module_from_spec(spec)
                        spec.loader.exec_module(module)

                        # Look for plugin classes
                        for attr_name in dir(module):
                            attr = getattr(module, attr_name)
                            if isinstance(attr, type) and hasattr(attr, "protocol_name"):
                                plugins.append({
                                    "name": getattr(attr, "plugin_name", attr_name),
                                    "version": getattr(attr, "plugin_version", "0.1.0"),
                                    "description": getattr(attr, "__doc__", ""),
                                    "protocol_name": getattr(attr, "protocol_name", "custom"),
                                    "module_name": filename[:-3],
                                    "class_name": attr_name,
                                    "file_path": file_path,
                                })
                except Exception as e:
                    logger.warning(f"Failed to scan plugin {filename}: {e}")

        return plugins


plugin_service = PluginService()
