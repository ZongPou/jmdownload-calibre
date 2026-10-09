"""插件用户配置：JSONConfig 持久化到 calibre 配置目录。"""

from calibre.utils.config import JSONConfig

from calibre_plugins.jmcomic2calibre.common import DEFAULTS

prefs = JSONConfig("plugins/jmcomic2calibre", defaults=DEFAULTS)
