# 哔哩轻小说下载器：简体界面与代理版

基于 [allen3206/BiliNovelDownloader](https://github.com/allen3206/BiliNovelDownloader) 的 Windows 桌面分支。提供简体界面、HTTP 代理设置，以及明确结束的单次下载任务。

## 使用

1. 在 [Releases](https://github.com/EyeMelody/BiliNovelDownloader/releases) 下载 Windows 64 位 ZIP，完整解压。
2. 双击 `BiliNovelDownloader.exe`；保留同目录 `tools` 文件夹，不需要安装 Python 或 Dart。
3. 如需代理，打开菜单 **代理设置**，勾选启用，填写 `http://127.0.0.1:7890`，测试连接后保存。
4. 输入小说网址或数字 ID，选择全部卷或指定范围（如 `1,3-5`），开始下载。
5. 结果位于 `downloads/简体/书名` 和 `downloads/繁体/书名`。

支持 `www/tw/m.linovelib.com` 和 `bilinovel.com/net` 网址；书籍预览会规范化为 `www.bilinovel.com` 手机站请求，以避免旧版固定访问繁体桌面站造成的兼容性问题。网站仍可能拒绝或限制请求，代理不能保证消除所有 403。

## 本分支的修改

- 界面、菜单、对话框和应用提示使用简体中文，书籍预览也转为简体。
- 显式 HTTP/混合代理设置覆盖预览、目录、封面、正文、插图、网站脚本和更新检查。关闭代理时直连，不依赖系统代理或 TUN。暂不支持 SOCKS、代理账号密码。
- 用单次 JSON 任务替代 stdin 模拟选项输入；单卷不会因为跳过“合并”问题而把章节标题选项错位。
- 配套核心在任务完成后正常退出，刷新日志并发送完成标记；应用同时检查退出码、完成标记、EPUB 数量与结构。真正的卡住仍保留 15 分钟停滞保护、6 小时总上限和取消操作。
- 每次下载使用独立 `temp/job-*` 目录，保留源文件和失败日志，不清空历史任务。临时目录需要时可由用户手动整理。
- 简体成品实际进行 OpenCC 转换，不再仅把源文本复制进名为“简体”的文件夹。目录和元数据一起转换，图片和资源路径保持原样。

**必须使用本分支附带的 `bili_novel_packer-0.2.49-gui.exe`，不要替换成上游交互版核心。升级请整包更新。**

## 构建

使用 Windows x64、Python 3.12/3.13、Dart 3.13.5。核心源码位于 `vendor/packer`，上游版本和提交记录见该目录 `UPSTREAM.md`；保留了上游 MIT 授权。

```powershell
python -m pip install -r requirements.txt pyinstaller
Push-Location vendor/packer
dart pub get --enforce-lockfile
dart compile exe bin/gui.dart -o ../../tools/bili_novel_packer-0.2.49-gui.exe
Pop-Location
./packaging/build_release.ps1
```

打包脚本不会批量删除旧构建目录；若同名发行目录已经存在，会提示停止。

## 测试

```powershell
python -m unittest discover -s tests -v
Push-Location vendor/packer
dart analyze bin/gui.dart lib/gui_proxy.dart
dart test test/gui_proxy_test.dart
Pop-Location
```

Python 测试覆盖单卷/多卷/合并、标题选项、取消、停滞、失败完成标记、代理设置和 EPUB 简体转换。Dart 测试用本地代理接收来自两个独立客户端的正文和图片请求，确认请求确实经过代理。Python 测试产物保留在被 Git 忽略的 `.test-runs` 目录。

已通过一次真实单卷回归：从繁体站网址输入，使用本机 7890 代理下载《无职转生～蛇足篇～》第 1 卷，约 213 秒完成核心退出和双版本转换。这是当次验证结果，不保证站点改版后始终可用。

## 授权

应用上游：allen3206/BiliNovelDownloader，MIT。

下载核心上游：Montaro2017/bili_novel_packer 0.2.49，MIT。修改为新增单次任务入口和代理策略，上游抓取与排版实现保留。

请保留 `LICENSE`、`NOTICES.txt` 和第三方授权文件。程序只提供下载及本地排版功能，不随软件分发小说内容。
