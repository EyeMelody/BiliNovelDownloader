# 使用说明：简体界面 / 代理 / 单次任务版

1. 完整解压后双击 BiliNovelDownloader.exe，不要只移动 EXE，保留旁边的 tools 文件夹。
2. 菜单「代理设置」中勾选「启用代理」，填入 http://127.0.0.1:7890，测试并保存。
   支持 HTTP/混合代理，无需 TUN；设置覆盖预览、正文、插图和更新检查。
   关闭时使用直连。暂不支持 SOCKS 或带账号密码的代理。
3. 输入书籍网址或数字 ID，选择全部卷或指定范围，然后开始下载。
   接受 www/tw/m.linovelib.com 和 bilinovel.com/net，预览统一使用手机站。
4. 下载结果保存在 downloads/简体 和 downloads/繁体，正文与目录都会实际转换。
   图片原样保留，图片里的文字不会自动转换。
5. 核心下载结束后立即退出，应用验证 EPUB 后转换，不再等待下一本输入。
   真正的下载停滞仍受 15 分钟保护；失败日志和原始内容保留在 temp/job-*。
6. 本版本必须搭配本分支的 *-gui.exe 核心，请从本分支整包更新，勿替换为上游交互版核心。
   https://github.com/EyeMelody/BiliNovelDownloader
