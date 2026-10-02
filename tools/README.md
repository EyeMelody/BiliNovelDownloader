# 核心下载器目录

请保持本目录与 BiliNovelDownloader.exe 在同一级目录。

本分支必须使用随安装包提供的 bili_novel_packer-0.2.49-gui.exe。它支持单任务退出和显式 HTTP 代理，不能直接替换成上游的交互版核心。

从源代码运行时，请按照项目 README 使用 Dart 3.13.5 编译 vendor/packer/bin/gui.dart，并将产物放到本目录。可执行文件不提交到 Git 仓库。

核心基于 Montaro2017/bili_novel_packer（MIT），来源与修改见 vendor/packer/UPSTREAM.md，许可证见 LICENSE-bili_novel_packer.txt。
