# 哔哩轻小说下载器：简体界面与代理版

基于 [allen3206/BiliNovelDownloader](https://github.com/allen3206/BiliNovelDownloader) 的 Windows 桌面分支。提供简体界面、HTTP 代理设置，以及对上游原版下载核心的交互适配。

## 使用

1. 在 [Releases](https://github.com/EyeMelody/BiliNovelDownloader/releases) 下载 Windows 64 位 ZIP，完整解压。
2. 双击 `BiliNovelDownloader.exe`；保留同目录 `tools` 文件夹，不需要安装 Python 或 Dart。
3. 如需代理，打开菜单 **代理设置**，勾选启用，填写 `http://127.0.0.1:7890`，测试连接后保存。默认关闭，保存后记住选择；此选项仅作用于 GUI 请求。
4. 输入小说网址或数字 ID，选择全部卷或指定范围（如 `1,3-5`），开始下载。
5. 结果位于 `downloads/简体/书名` 和 `downloads/繁体/书名`。

支持 `www/tw/m.linovelib.com` 和 `bilinovel.com/net` 网址；书籍预览会规范化为 `www.bilinovel.com` 手机站请求，以避免旧版固定访问繁体桌面站造成的兼容性问题。网站仍可能拒绝或限制请求，代理不能保证消除所有 403。

## 本分支的修改

- 界面、菜单、对话框和应用提示使用简体中文，书籍预览也转为简体。
- GUI 的 HTTP/混合代理覆盖预览、目录、封面和更新检查，默认关闭。原版核心不接收 GUI 代理参数，其正文和插图下载保持原版网络行为；需要代理时请使用能正常运行原版核心的网络/TUN 环境。暂不支持 SOCKS、代理账号密码。
- GUI 按原版核心实际提示逐项输入，并保持 stdin 打开；单卷跳过“合并”问题时，不会造成章节标题选项错位。
- 原版核心完成后继续等待下一本是正常行为。GUI 在收到下一次链接提示后，核对打包完成次数、EPUB 数量与结构，再结束自己启动的核心进程。不会仅凭出现 EPUB 就判为成功。真正的停滞仍保留 15 分钟保护、6 小时总上限和取消操作。
- 每次下载使用独立 `temp/job-*` 目录，保留源文件和失败日志，不清空历史任务。临时目录需要时可由用户手动整理。
- 简体成品实际进行 OpenCC 转换，不再仅把源文本复制进名为“简体”的文件夹。目录和元数据一起转换，图片和资源路径保持原样。

**v1.6.2 起使用上游原版核心。更新检查分别查询本分支应用和 Montaro2017/bili_novel_packer；将上游 Windows EXE 放入 tools 即可，优先选择版本号最高的非 GUI 核心。以后上游若改变交互提示，GUI 可能需要相应适配。**

## 构建

使用 Windows x64 和 Python 3.12/3.13。无需编译 Dart 核心，直接下载上游原版发布文件。

```powershell
python -m pip install -r requirements.txt pyinstaller
gh release download v0.2.49 --repo Montaro2017/bili_novel_packer --pattern '*x86_64-windows.exe' --dir tools
./packaging/build_release.ps1
```

本版核心 SHA-256：`c78c4dc58ba88610c65dcd44c817e3d93b783296340c1b847835acf8e56bb4a3`。
`vendor/packer` 仅保留前版源码供历史参考，不参与当前构建和运行。

打包脚本不会批量删除旧构建目录；若同名发行目录已经存在，会提示停止。

## 测试

```powershell
python -m unittest discover -s tests -v
```

Python 测试覆盖单卷/多卷/合并、标题选项、取消、停滞、失败完成标记、代理设置和 EPUB 简体转换。原版核心通过发布文件哈希校验，GUI 测试模拟原版无换行提示与持续等待下一本的行为。Python 测试产物保留在被 Git 忽略的 `.test-runs` 目录。

v1.6.0 的定制核心曾通过一次真实单卷回归（不代表当前原版核心的测试结果）：从繁体站网址输入，使用本机 7890 代理下载《无职转生～蛇足篇～》第 1 卷，约 213 秒完成核心退出和双版本转换。这是当次验证结果，不保证站点改版后始终可用。

## 授权

应用上游：allen3206/BiliNovelDownloader，MIT。

下载核心上游：Montaro2017/bili_novel_packer 0.2.49，MIT。当前发行包使用上游未修改的 Windows EXE。

请保留 `LICENSE`、`NOTICES.txt` 和第三方授权文件。程序只提供下载及本地排版功能，不随软件分发小说内容。
