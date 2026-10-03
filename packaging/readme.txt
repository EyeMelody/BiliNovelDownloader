# 简体界面 / 原版核心

完整解压后运行 BiliNovelDownloader.exe，保留 tools 文件夹。
当前包使用上游原版 v0.2.49 核心，未修改。
输入书籍网址或 ID，选择分卷，下载结果位于 downloads/简体 和 downloads/繁体。
GUI 根据实际提示填写选项；核心完成后回到链接输入时，GUI 校验 EPUB 并结束该核心进程，避免误等 15 分钟。
代理默认关闭，可手动开启并保存；该选项用于书籍预览、目录、封面和更新检查。
原版核心的正文与插图下载沿用自身网络行为，需要代理时请使用能正常运行原版核心的网络/TUN 环境。
检查更新分别查询本分支和核心上游，可下载原版 Windows 核心放入 tools；优先使用最高版本，忽略 *-gui.exe。
本分支：https://github.com/EyeMelody/BiliNovelDownloader
核心：https://github.com/Montaro2017/bili_novel_packer
