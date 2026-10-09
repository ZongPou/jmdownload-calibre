# jmdownload-calibre

一个车牌，把jm本子导入至Calibre书库并自带元数据，无需手动编辑。

下载 → 转 PDF/CBZ → 生成 `metadata.opf` → 导入 Calibre，标题、作者、标签、简介一次到位。

> One command to get your JMComic albums into Calibre — download, convert, tag, import.

## 插件功能

输入一个或多个 JM 漫画 ID（也支持网页链接），点击下载即可自动获取漫画、打包 CBZ 并导入当前 Calibre 书库。

插件会自动写入标题、作者、标签、简介、发布日期和封面等元数据，无需手动整理文件或编辑书籍信息；同时支持批量输入、重复检测、进度显示、取消下载和日志诊断。

### 安装插件

1. 前往本项目的 [Releases 页面](https://github.com/ZongPou/jmdownload-calibre/releases)，下载最新版本的 `jmdownload-calibre-v<version>.zip`。
2. 打开 Calibre：**首选项 → 插件 → 从文件加载插件**，选择下载的 zip。
3. 确认安装并重启 Calibre。
4. 在系统 Python 中安装下载引擎：

   ```bash
   python -m pip install jmcomic
   ```

插件不会把 jmcomic 及其二进制依赖打进 zip，而是调用系统 Python。安装后可在 **JMdownload → 环境检测** 中确认解释器和 jmcomic 是否可用。

### 使用插件

1. 点击 Calibre 工具栏中的 **JMdownload**。
2. 输入一个或多个漫画 ID/网页链接，每行一个；空行和 `#` 注释行会被忽略。
3. 点击下载。插件会显示每本漫画的进度，完成后将带有标题、作者、标签、简介、日期和封面的 CBZ 直接导入当前书库。

插件还支持：

- `jmcomic:<id>` 精确判重，已入库项目自动跳过
- `url:` 标识符，支持从书籍元数据回到漫画页面
- 代理、临时目录、解释器和网站域名配置
- 会话日志复制与环境诊断

## 环境要求

- Python 3.9+
- Calibre（`calibredb` 在 PATH 里）
- `img2pdf`（转 PDF 时需要，装 `[pdf]` extra 即可）

`--format cbz` 只需要标准库，不用额外依赖。

## 许可证

本项目基于 [MIT License](LICENSE) 发布。

Copyright (c) 2026 yifenliwu

## 致谢

- [jmcomic-calibre](https://github.com/yifenliwu/jmcomic-calibre) —— 本项目的上游。本插件由其 `jmcal` CLI 改造而来，图片自然排序打包与 OPF 元数据生成逻辑源自上游实现。
- [jmcomic](https://pypi.org/project/jmcomic/) —— 提供漫画下载引擎。
- [Calibre](https://calibre-ebook.com/) —— 本插件基于其插件接口开发。

上述第三方软件遵循其各自的原许可证，本项目不包含、不重新分发其代码。
