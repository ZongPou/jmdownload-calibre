# jmcomic-calibre

一条命令，把 JMComic（禁漫）的本子整理进 Calibre 书库。

下载 → 转 PDF/CBZ → 生成 `metadata.opf` → 导入 Calibre，标题、作者、标签、简介一次到位。

> One command to get your JMComic albums into Calibre — download, convert, tag, import.

## 为什么做这个

用 JMComic 存本子的人，很多最后都会用 Calibre 管书库：能搜、能读、能同步到 Kindle。但这两步之间一直缺一环——图片下载下来是散的，Calibre 又只认带元数据的电子书，手动一本本转 PDF、填标题作者标签，几十本就受不了了。

这个工具就是把中间那一段接上：给一个本子 id，剩下的全自动。

## 安装

```bash
pip install jmcomic-calibre[pdf]
```

还需要本机装好 [Calibre](https://calibre-ebook.com/)，并确保 `calibredb` 在 PATH 里。

## 用法

```bash
# 先看看环境齐不齐
jmcal doctor

# 下载 123456 并导入默认书库（默认转 PDF）
jmcal add 123456

# 指定书库和格式
jmcal add 123456 --library "D:/Calibre Library" --format cbz

# 先跑一遍确认没问题，不写进书库
jmcal add 123456 --dry-run

# 想自己看看临时文件
jmcal add 123456 --work-dir ./tmp --keep-workdir
```

## 它替你做了什么

1. 用 `jmcomic` 下载本子
2. 图片按**自然顺序**转成 PDF 或 CBZ —— `10.jpg` 不会被排到 `2.jpg` 前面
3. 生成 `metadata.opf`：标题、作者、标签、简介、发布时间；identifier 用 `jmcomic:<id>`，所以重复导入能被 Calibre 识别为同一本
4. `calibredb add` 导入，再用 `set_metadata` 把元数据写进去

## 作为库使用

jmcomic 内置的 `calibre_metadata` 插件，其 OPF 生成逻辑就是调用的这个库——两边共用一份实现，不需要各维护一份 XML 拼接代码。

```python
import jmcomic_calibre

jmcomic_calibre.export_opf(
    album=album,                 # jmcomic 的 JmAlbumDetail
    opf_path="Bd/123456/metadata.opf",
    fields={"language": "zh"},   # title/author 可覆盖默认值，其余键须是 Dublin Core 元素名
    include_cover=True,
    download_cover=lambda path: downloader.client.download_album_cover(album.id, path, ""),
)
```

装了这个库，jmcomic 的 `calibre_metadata` 插件会自动切到这份实现；没装的话插件会提示 `pip install jmcomic-calibre` 并跳过。

只想拿 XML 字符串、不落盘，可以用更底层的 `build_opf(AlbumMeta)`；`DUBLIN_CORE_ELEMENTS` 是对外暴露的合法字段白名单。

## 环境要求

- Python 3.9+
- Calibre（`calibredb` 在 PATH 里）
- `img2pdf`（转 PDF 时需要，装 `[pdf]` extra 即可）

`--format cbz` 只需要标准库，不用额外依赖。

## Roadmap

- [x] 下载 → 转格式 → 写元数据 → 导入 Calibre
- [ ] 批量导入：一次给一串 id
- [ ] 跳过已入库的本子（按 `jmcomic:<id>` 判重）
- [ ] 封面自动抓取并写入书库

## English

`jmcomic-calibre` imports JMComic albums into a Calibre library in one command:

```bash
pip install jmcomic-calibre[pdf]
jmcal doctor
jmcal add 123456 --library "/path/to/Calibre Library" --format pdf
```

It downloads the album via `jmcomic`, converts the images to PDF or CBZ in natural page order,
writes a `metadata.opf` (title / authors / tags / description / date, with a `jmcomic:<id>`
identifier so Calibre can detect duplicates), then runs `calibredb add` followed by
`set_metadata`.

Requirements: Python 3.9+ and Calibre (`calibredb` on PATH).

The OPF generation is also exposed as a library API (`jmcomic_calibre.export_opf`) and is what
jmcomic's built-in `calibre_metadata` plugin calls, so the XML logic lives in one place.

## License

MIT
