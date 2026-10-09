"""插件用户配置：JSONConfig 持久化到 calibre 配置目录。

注意：新版 calibre（9.x）的 JSONConfig 不再支持 defaults 构造参数
（签名只有 rel_path/base_path/permissions），改用 setdefault 注入
默认值：已存在的用户配置保持不变，缺失的键写入默认值。
"""

from calibre.utils.config import JSONConfig

from calibre_plugins.jmcomic2calibre.common import DEFAULTS

prefs = JSONConfig("plugins/jmcomic2calibre")
for _key, _value in DEFAULTS.items():
    prefs.setdefault(_key, _value)
