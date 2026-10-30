# AGENTS.md

本项目由 AI 编码代理协作开发。本文件是跨会话/跨工具的上下文锚点，决策变更时须同步更新。

## 项目目标与当前状态

把上游 CLI 工具（jmcomic-calibre，`jmcal` 命令）改造为 **Calibre GUI 插件**：
输入禁漫漫画 ID → 自动下载 → 打包 CBZ（内嵌 ComicInfo.xml）→ 带元数据直接入库 Calibre。

**当前状态：v0.3.5 本地候选版，基于 v0.3.4（f7e5a22）仅移除额外封面提取；保留新版 UI 和全部其他功能。v0.3.3（f03b69d）为任务行操作，v0.3.2（521eb2e）为命名调整，v0.3.1（c67d642）为速度优化。待用户真实站点 / Calibre GUI 验收；v0.2.7 阶段 1-4 已验收。**
- 历史：v0.2.8 将章节 / 图片并发限制为 1 / 4，降低大合集连接数；v0.3.1 按用户明确要求提高到 1 / 16，不能认定站点限流或网络问题已解决。
- 新构建：`dist/jmdownload-calibre-v0.3.5.zip`；保留旧版本 zip。
- 测试：`python -m unittest tests.test_plugin`，59 项；真实 Qt 离线冒烟 `calibre-debug -e tests/gui_smoke.py`，22 项。后者启动前应将 `CALIBRE_CONFIG_DIRECTORY` 指向工作区 `.qa-calibre`，隔离用户配置。
- v0.3.5 用户明确范围：不是回退整个 v0.2.8，仅取消额外的网络封面提取。移除 CoverWorker / 封面槽与封面 CLI；预读只请求漫画详情提取章节列表，不预取各章详情或封面。保留配置门槛、章节勾选 / 范围选择、下载中追加、行内修改 / ×、命名、16 图并发、详情复用和新版 UI。队列原封面位置使用插件本地图标，无网络；Calibre 入库封面仍从已下载首页本地生成。v0.3.4 的独立纵向封面功能已被此要求替代。
- 速度边界：比对 v0.2.8 源码确认其未实现章节选择，也未额外请求封面。当前仍为章节预读 / 下载两个进程，网络初始化与接口响应时间尚存在；删除封面进程会减少请求，但不得宣称已恢复旧版速度或解决接口响应慢。
- v0.3.3 用户界面要求：下载弹窗移除“取消当前任务 / 取消所选任务 / 修改所选任务章节 / 重新检测环境 / 配置”按钮，“添加到队列”改为“添加并下载”；底部仅复制日志 / 添加并下载 / 关闭。每条任务右侧“修改”仅在等待中启用，最右侧“×”直接从列表移除；活动下载或预读先取消后台工作，保留线程引用至 finished 后接续队列；迟到事件不重建被移除的行。已完成记录移除不删书库。配置 / 环境检测仍在工具栏菜单。使用 TaskRow 行控件承载封面和操作，不同时设置原生 item icon，避免双封面占位。
- v0.3.2 用户命名要求：Calibre 书名、CBZ 文件名、ComicInfo.xml 标题与已选队列标题统一为“鬼畜英雄 第1-10话”格式；全本也带范围，单话为“第3话”，非连续为“第1-3、5话”。仅去除标题开头的 `[...]` / `【...】` 附注，不改作者元数据，整段书名都在括号中时保留。修改章节时同步重新生成命名；不追溯改动已入库书籍。
- 2026-10-31：新增可配置自动下载集数门槛（默认 3，0 为始终选择）、章节勾选 / 范围批量选择、下载中追加 ID、队列封面缩略图。离线测试与离屏布局检查通过，真实下载与内容 QC 未执行。
- 2026-10-31：用户日志确认 v0.3.0 选集下载前串行统计 10 章耗时 131 秒，存在重复漫画 / 章节查询。v0.3.1 预读以 JSON 快照传漫画详情，下载复用 option.build_jm_client 的连接；逐章 get_photo_detail(fetch_album=False) 后直接下载该详情，禁止重新按 ID 下载，保留失败检查。选集总页数未知时显示张数，最后一章详情就绪后切换精确百分比。离线验证顺序和请求次数，不宣称实际网络提速比例。
- v0.3.1 队列管理基础：仅等待中的任务可修改章节（恢复原勾选，取消编辑保留原选择）。编辑期间状态为“修改章节中”，阻止自动开始该任务；取消预读后丢弃迟到结果，防止复活任务或误更新同 ID 的新任务。v0.3.3 用行内修改 / 移除替代所选任务按钮与多选取消。
- 旧发布交接简报：`reports/release/release-v0.2.7_review_brief.md`，只适用于 v0.2.7；新候选版未发布。

## 功能清单（v0.3.5 候选版）

- 批量输入漫画 ID/网页链接（自动提取 ID、去重、注释行支持）
- 子进程桥调用系统 Python 的 jmcomic 下载（防黑框、可取消、取消清理半成品）
- 自然排序打包 CBZ（内嵌 ComicInfo.xml，Anansi 规范）
- 元数据随书入库（标题/作者/标签/简介/日期/封面，legacy add_books 路径，视图即时刷新）
- 双标识符：`jmcomic:<id>` 判重 + `url:` 可点击跳转（域名可配置）
- 判重跳过（identifiers 精确搜索）
- 精确进度条（全本 page_count 百分比；选集逐章统计，全部选集页数确定前显示已下载张数，确定后显示 n/total 与百分比）
- 工具栏分体按钮 + 下拉菜单（下载/配置/环境检测）
- 配置面板（解释器/域名/代理/临时目录/判重开关/保留开关 + 环境测试按钮）
- 会话日志一键复制（状态变化全记录 + 失败堆栈 + jmcomic 日志尾部，环境头信息）
- 后台仅预读章节，超过配置门槛时立即弹窗，支持 `1-10、12、15-18`，弹窗不显示门槛，不请求封面。
- 窗口内顺序队列：下载中继续追加 ID、活跃 ID 去重、默认图标 / 章节 / 状态展示；当前任务取消后继续队列，关闭窗口取消后台任务并等线程退出。队列不跨窗口持久化。
- 选集打包为一本 CBZ，标题标注章节范围；始终保留 `jmcomic:<原ID>` / `url:`，选集附加 `jmchapters:` 标识符以区别不同选择，已有全本会跳过选集。
- 按章节顺序逐集下载，输出唯一章节 / 页码文件名，避免多集图片交错或 CBZ 重名；每次任务使用独立临时目录，防止混入旧任务图片。封面预览独立保存，不进入 CBZ。

## 冻结的架构决策与踩坑清单（勿推翻；新代码必须遵守）

- **2026-10-31 用户明确调整并发**：章节仍为 1，图片上限从 4 提高至 16；复用漫画和章节详情，取消下载前遍历所有选集统计页数，后续章节页数随下载逐步读取。

- **下载引擎**：子进程桥调用系统 Python 的 jmcomic（curl-cffi/pycryptodome 为二进制依赖，无法进插件 zip）。
- **bridge 必须 sys.path 隔离**：jmcomic 内部有裸导入 `from common import ...`，
  脚本目录若有 common.py 会劫持（已实现 `_isolate_script_dir`，勿删）。
- **入库走 legacy 层** `gui.current_db.add_books([cbz], ['CBZ'], [mi], return_ids=True)`。
  **严禁 new_api.add_books 直写**——不同步 GUI 数据缓存，需重启才可见（实测踩坑）。
- **判重**：`db.new_api.search('identifiers:"=jmcomic:<id>"')`（Cache 没有 get_book_id_from_identifier）。
- **worker 信号命名**：禁止叫 `event`（遮蔽 QObject.event → "native Qt signal is not callable" 闪退，
  已改名 message_received）。
- **QThread 生命周期**：无 Qt parent；`finished` → UI 复位 + `deleteLater`；结束后不解除
  Python 引用（提前置 None 会被 GC 析构致闪退，实测踩坑）。
- **防黑框**：所有 subprocess（worker/doctor）Windows 上必须 `creationflags=CREATE_NO_WINDOW`。
- **get_icons/get_resources** 是插件系统注入的 builtins，直接调用、**不要 import**
  （新版 calibre.gui2 顶层没有 get_icons，import 即炸）。
- **JSONConfig**（calibre 9.x）无 defaults 构造参数，用 setdefault 注入默认值。
- **books_added(num) 必须传数量**；入库后需手动触发视图刷新（books_added/refresh_cover_browser/
  tags_view.recount，各步骤独立容错）。
- **配置界面**：is_customizable/config_widget/save_settings 须在**包装类与 actual plugin 两边都实现**
  （首选项面板检查包装类）；ConfigWidget 的 Qt 导入延迟到方法调用。
- **identifier**：双写 `jmcomic:<id>`（判重）+ `url:<域名>/album/<id>/`（跳转，域名可配置）。
- **ComicInfo.xml** 定位是文件自描述与第三方阅读器兼容；**Calibre 导入 CBZ 不读它**（源码已核实）。
- **metadata.opf** 由 Calibre 入库后自动生成，插件不生成不导入。
- **测试纪律**：提交前必须 `python -m unittest tests.test_plugin` 全过——
  串行命令里测试失败后仍会继续打包提交（踩过），测试与提交分开跑。

## 环境信息（用户机器：Windows / PowerShell）

- Calibre 9.15（内嵌 Python 3.14；JSONConfig 无 defaults 参数，用 setdefault 注入默认值）
- 系统 Python 3.13.13 @ `C:\Program Files\Python313\python.exe`；jmcomic 2.7.8（--user 安装）
- 公开仓库目标：`ZongPou/jmdownload-calibre`；内部插件包名保持 `jmcomic2calibre`
- git remote：当前工作区仍指向旧远程，待用户在 GitHub 完成仓库改名后再更新 remote
- 本地仓库根 = 工作区根 `c:/Users/zongp/Documents/ChatGPT/jmcomic2calibre`
- 诊断脚本：`scripts/diag_meta.py`（查元数据定位网络问题）、`scripts/diag_fields.py`（字段探测）、
  bridge.py `--meta-only`

## 分工边界（重要）

- 代理：代码、离线单测（不碰网络）、构建 zip、git 提交
- 用户：真实站点联调、Calibre GUI 验收、内容 QC、GitHub push/Release（需用户凭证）
- 测试：`python -m unittest tests.test_plugin`（59 项，全离线）；`tests/gui_smoke.py` 另有 22 项真实 Qt 离线测试，不连接站点 / 书库。

## 阶段计划与进度

1. [x] 插件骨架（对话框/JSONConfig/doctor/构建脚本）
2. [x] 子进程下载桥（JSON-lines 事件协议/进度轮询/取消）
3. [x] 入库（CBZ+ComicInfo.xml+legacy add_books/判重/双标识符/封面/视图即时刷新）
4. [x] 打磨（4A 配置面板 / 4B 精确进度条 / 4C 下拉菜单 / 4D 日志一键复制 /
       取消闪退修复 / 中途取消清理半成品 / 防黑框全覆盖）
5. [ ] **发布（进行中，交接简报见 reports/release/）**：
   - 用户验收候选版后 push 本地未推送提交到 origin/main（需用户凭证）
   - 打 tag `v0.2.7` 并推送
   - 创建 GitHub Release：标题 `v0.2.7`，上传 `dist/jmdownload-calibre-v0.2.7.zip`，
     说明文案见交接简报第三节
   - README 已包含插件安装 / 使用说明；v0.3.5 安装包待 GUI 与真实站点验收后再制定对应 Release

## 协作约定

- 每轮任务完成后 git 暂存提交；提交信息按阶段浓缩关键词
- 提交前必须先跑测试全过（测试与提交分开执行）
- 不生成一次性总结报告文件；AGENTS.md 是唯一持久上下文，
  交接/验收关口另出 reports/ 简报
- 遇到需要推翻"冻结决策/踩坑清单"的想法：先向用户陈述理由，获同意后改本文件再动代码
