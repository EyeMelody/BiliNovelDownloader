> 本项目为 [allen3206/BiliNovelDownloader](https://github.com/allen3206/BiliNovelDownloader) 的 fork 分支版本。

<p align="center">
   <img src="./assets/icon.png" width="256" height="256" />
</p>

<h1 align="center">哔哩轻小说自动下载与繁化工具 (BiliNovelDownloader)</h1>

基于 [bili_novel_packer](https://github.com/Montaro2017/bili_novel_packer) 核心打造的图形化介面工具，专为 [哔哩轻小说](https://tw.linovelib.com/) 而设计。支援小说资讯预览、全自动下载及 EPUB 简繁转换。

## 预览

<img width="952" height="732" alt="screenshot1" src="./assets/screenshots1.png" />

<img width="952" height="732" alt="screenshot2" src="./assets/screenshots2.png" />

<img width="952" height="732" alt="screenshot3" src="./assets/screenshots3.png" />

## 特色与功能

*   **图形介面**：贴上网址或数字 ID 即可预览小说资讯（封面、简介、目录）
*   **简繁转换**：原站仅提供简体版，程式下载完成后自动透过 `opencc` 转换，同时输出简体与繁体两份 EPUB（含资料夹与档案名称），分别存放于 `downloads/简体/` 与 `downloads/繁体/`
*   **即时状态追踪**：内建执行日志与进度提示，及时查看下载资讯、错误讯息
*   **分卷下载**：可选下载 **全部范围** 或 **指定范围**（例如：`1, 3-5, 9`）
*   **进阶整合选项**：可选择「合并选取的分卷为单一档案」，或是「在每章开头自动添加章节标题」
*   **下载历史纪录**：自动储存近期载入过的小说网址，点击下拉选单即可重新载入
*   **智慧快取机制**：书籍封面图片自动快取 24 小时，提升二次载入速度

## 如何使用

**系统需求**：Windows 10 / 11（64 位元）

1. 前往 [Releases 页面](https://github.com/EyeMelody/BiliNovelDownloader/releases) 下载最新的 `.zip` 压缩档
2. 将下载的压缩档 **解压缩** 到电脑中（例如：桌面或 D 槽）
3. 打开解压缩后的资料夹，会看到以下结构：
   ```text
   BiliNovelDownloader-...-windows-x64/
   ├── BiliNovelDownloader.exe             (主程式)
   ├── readme.txt                             (使用须知)
   ├── LICENSE.txt
   ├── NOTICES.txt
   ├── THIRD_PARTY_LICENSES.txt
   └── tools/
       ├── bili_novel_packer-xxx-windows.exe  (核心下载器)
       └── LICENSE-bili_novel_packer.txt
   ```
4. **双击 `BiliNovelDownloader.exe` 即可开始使用**

下载完成后，档案会存放于以下结构：
```text
downloads/
├── 简体/
│   └── 书名/
│       ├── 书名 第1卷.epub
│       └── 书名 第2卷.epub
└── 繁体/
    └── 书名/
        ├── 书名 第1卷.epub
        └── 书名 第2卷.epub
```

> **提醒：**
> *   不要在未解压缩的 ZIP 档内直接执行程式
> *   请务必保持 `exe` 主程式与 `tools` 资料夹在同一层目录下。如果想将捷径放在桌面，请对 `exe` 按右键选择「建立捷径」并移至桌面，切勿单独将 exe 档案移走

## 授权与声明

*   授权条款：[MIT License](LICENSE)
*   本专案核心下载功能使用 [bili_novel_packer](https://github.com/Montaro2017/bili_novel_packer)
*   本工具仅供学习与交流使用，请勿用于商业用途或大量恶意抓取

## 下载器核心更新

如果未来遇到可用的更新版本：

1. 前往核心下载器原作者的 GitHub：[Montaro2017/bili_novel_packer](https://github.com/Montaro2017/bili_novel_packer/releases)
2. 下载最新版本的 `bili_novel_packer-...-windows.exe`
3. 移除旧版本下载器，将下载的新档案移至本工具 `tools` 资料夹内即可正常运作

---

## 原始码

如想修改程式码，请参考以下说明：

### 环境准备

1. 建议使用 Python 3.10 以上
2. 安装必要的套件：
   ```bash
   pip install -r requirements.txt
   ```

### 直接执行脚本

在专案根目录下执行：
```bash
python BiliNovelDownloader.py
```

### 打包成 exe

```bash
pyinstaller BiliNovelDownloader.spec
```