# 发布交接简报：release-v0.2.7

生成：2026-10-10 | 移交方：CodeBuddy（开发代理） | 接收方：外部发布代理

## 一、任务定义与验收标准

**任务**：将本地 v0.2.7 插件发布到 GitHub（目标仓库：ZongPou/jmdownload-calibre）。

**发布物（已构建，勿重新构建）**：`dist/jmdownload-calibre-v0.2.7.zip`（构建产物，
由 `python build_plugin.py` 从 `calibre_plugin/` 打包，顶层含 `__init__.py` 与
`plugin-import-name-jmcomic2calibre.txt`）。

**验收标准**：
1. 25 个本地提交全部推送到 `origin/main`
2. tag `v0.2.7` 存在于 origin 并指向推送后的最新提交
3. GitHub Release 页面出现 Release，附有上述 zip 资产
4. 仓库 README 与插件实际功能一致（需增补插件章节，见第三节文案）
5. 发布后 `git status` clean、本地与 origin 同步

## 二、必读文件入口

| 文件 | 作用 |
|---|---|
| `AGENTS.md` | **先读**。项目全貌、架构决策、踩坑清单（9 条实测教训）、分工边界 |
| `dist/jmdownload-calibre-v0.2.7.zip` | 发布物（.gitignore 已忽略 dist/，不入库，直接上传） |
| `calibre_plugin/` | 插件源码（zip 的内容源） |
| `tests/test_plugin.py` | 45 项离线单测 |
| `build_plugin.py` | 构建脚本（仅当需要重新打包时使用） |
| `README.md` | 项目总览、Calibre 插件安装/使用说明与 CLI 可选用法 |

## 三、口径约定（Release 文案与命名）

- 插件展示名：**JMdownload**；仓库/项目名：jmdownload-calibre；内部包名：jmcomic2calibre
- 版本口径：语义化 `v0.2.7`；zip 文件名：`jmdownload-calibre-v0.2.7.zip`
- Release 标题草案：`v0.2.7 — JMdownload（Calibre 漫画下载入库插件）`
- Release 说明草案（可直接用）：
  - 功能：输入禁漫漫画 ID/链接 → 自动下载 → 打包 CBZ（内嵌 ComicInfo.xml）→ 带元数据入库 Calibre；
    支持批量、判重跳过、精确进度、取消、会话日志一键复制、图形化配置
  - 安装：Calibre → 首选项 → 插件 → 从文件加载插件 → 选择 zip → 重启；
    另需系统 Python 并 `pip install jmcomic`（插件会自动探测）
  - 环境：Calibre ≥ 7.0（9.15 实测）；Python ≥ 3.9（3.13 实测）
- 提交信息口径：中文短语，"阶段/类型: 关键词"（历史 24 提交已符合，勿改写）

## 四、已知限制

- **push 与 Release 创建需要用户的 GitHub 凭证**：若 `gh` CLI 未登录或无凭证，
  停止操作并回报，由用户手动执行（网页或本机终端）
- `calibredb` 类命令在 Calibre GUI 运行时会被拒（库单开锁）——本任务不涉及，但勿尝试用
  calibredb 验证书库
- zip 为 .gitignore 忽略项：Release 上传后 dist/ 内历史版本 zip（v0.1.0~v0.2.6 共 8 个）
  留在本地即可，**不要**上传历史版本
- README 已加入 `docs/screenshots/jmdownload-window.png` 界面截图
- jmcomic 下载会在 %TEMP% 留下空 `.tmp*` 目录（上游库行为，未修复，README 可不提）

## 五、复现验证方式

```powershell
Set-Location "c:/Users/zongp/Documents/ChatGPT/jmcomic2calibre"
python -m unittest tests.test_plugin        # 期望：Ran 45 tests, OK
python -c "import sys; sys.path.insert(0,'.'); from build_plugin import read_version; print(read_version())"  # 期望：0.2.7
git log origin/main..HEAD --oneline | Measure-Object -Line   # 发布前应为 25
git status --short                           # 期望：空
```

发布后验证：`git ls-remote --tags origin` 应含 `v0.2.7`；Release 页面资产名与本地构建产物大小
（1,517,363 字节）一致。

## 六、回报格式与权限边界

**回报格式**（完成后输出）：
1. push 结果：推送的提交区间（起止短哈希）与是否成功
2. tag 结果：`v0.2.7` 指向的提交短哈希
3. Release 链接（URL）与资产校验（文件名 + 字节数）
4. README 改动摘要（改了哪些章节）
5. 遗留问题清单（如有）

**权限边界**：
- 允许：git push（origin main 与 tag）、gh release create、README 编辑、AGENTS.md 进度勾选
- 禁止：force push、改动 25 个提交本身（rebase/amend）、删除分支、修改 upstream 远程、
  重新构建 zip（以 dist/ 现有产物为准）、动 src/ 与 calibre_plugin/ 的代码
- 中止条件：gh 未登录、push 被拒（权限/远端变化）、任何非预期报错——回报后等用户指示
