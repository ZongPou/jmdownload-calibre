<p align="center">
  <img src="calibre_plugin/images/icon.png" alt="JMdownload 图标" width="180">
</p>

<h1 align="center">jmdownload-calibre</h1>

## 插件功能

- **下载导入**：输入 JM 漫画 ID 或网页链接，自动下载、打包 CBZ 并导入 Calibre。
- **自动元数据**：写入标题、作者、标签、简介、日期和封面，无需手动编辑。
- **批量管理**：支持多条输入、重复检测、进度显示、取消下载和日志诊断。
- **项目搭配**：结合 [calibre-metamanga](https://github.com/ZongPou/calibre-metamanga)，使用 AI 识别并更正元数据。
- **完整流程**：下载 → 打包 → 导入 → AI 校正，减少手动管理。

### 安装插件

- 前往本项目的 [Releases 页面](https://github.com/ZongPou/jmdownload-calibre/releases)，下载最新版本的插件 zip 包，不要解压。
- 打开 Calibre：**首选项 → 插件 → 从文件加载插件**，选择下载的 zip。
- 确认安装并重启 Calibre。
- 在系统 Python 中安装下载引擎：

   ```bash
   python -m pip install jmcomic
   ```

### 使用插件

- 点击 Calibre 工具栏中的 **JMdownload**。
- 输入一个或多个漫画 ID/网页链接，每行一个；空行和 `#` 注释行会被忽略。
- 点击 **添加到队列**。插件后台读取章节和封面，总集数不超过配置门槛（默认 3 集）时自动下载全部；超过时弹窗选择章节。
- 在章节弹窗中逐集勾选，或输入 `1-10`、`1-10、12、15-18` 等范围后点击 **应用范围**，再确认加入队列。
- 下载过程中输入框保持可用，可以继续追加 ID；队列显示封面缩略图、所选章节及状态，任务按添加顺序执行。
- 选中等待中的任务，点击 **修改所选任务章节** 可调整章节，原选择会自动勾选；点击 **取消所选任务** 可取消指定任务，支持 Ctrl / Shift 多选取消。正在下载的任务可取消，修改章节请取消后重新添加。
- 完成后将带有标题、作者、标签、简介、日期和封面的 CBZ 直接导入当前书库。部分章节的书名会标注范围；不同选集分别判重，已有全本时跳过选集。
- 点击 **配置** 修改自动下载集数门槛；设为 `0` 时始终选择章节。**取消当前任务** 只取消正在下载的漫画，其他任务继续执行；关闭窗口则结束整个队列。

封面读取失败时仍可选择章节和下载。待处理队列仅保留在当前窗口中，关闭后不会恢复。

下载按章节顺序进行，每章最多并发下载 16 张图片。漫画和章节详情会复用；选集无需等待全部章节页数统计完才开始下载。总页数未确定时显示已下载张数，确定后显示百分比。

插件还支持：

- `jmcomic:<id>` 精确判重，已入库项目自动跳过
- `url:` 标识符，支持从书籍元数据回到漫画页面
- 代理、临时目录、解释器和网站域名配置
- 会话日志复制与环境诊断

## 界面截图

![JMdownload 下载窗口](docs/screenshots/jmdownload-window.png)

JMdownload 窗口支持输入漫画 ID 或网页链接，并在下载前检测 Python 与 jmcomic 运行环境。

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
