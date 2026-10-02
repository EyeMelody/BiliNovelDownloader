import 'dart:convert';
import 'dart:io';
import 'package:bili_novel_packer/gui_proxy.dart';
import 'package:bili_novel_packer/logger.dart';
import 'package:bili_novel_packer/pack_option.dart';
import 'main.dart' as core;

/// A single job, no interactive stdin and no next-book loop.
Future<void> main(List<String> args) async {
  if (args.length == 1 && args[0] == '--capabilities') {
    stdout.writeln(jsonEncode({'protocol': 1, 'http_proxy': true}));
    return;
  }
  try {
    if (args.length != 2 || args[0] != '--gui-job') {
      throw const FormatException('请通过桌面应用启动，或传入 --gui-job job.json');
    }
    final job = jsonDecode(File(args[1]).readAsStringSync()) as Map<String, dynamic>;
    HttpOverrides.global = GuiProxyOverrides(parseGuiProxy(job['proxy']));
    final url = job['url'] as String;
    final source = core.detectSource(url);
    if (source == null) throw const FormatException('不支持的小说网址');
    logger.i('GUI protocol: 1; proxy: ${job['proxy'] ?? 'DIRECT'}');
    final novel = await source.getNovel(url);
    final catalog = await source.getNovelCatalog(novel);
    final requested = job['volumes'] as List<dynamic>?;
    final selected = requested == null ? catalog.volumes : requested.map((v) {
      if (v is! int || v < 1 || v > catalog.volumes.length) {
        throw FormatException('分卷编号超出范围：$v');
      }
      return catalog.volumes[v - 1];
    }).toList();
    if (selected.isEmpty) throw const FormatException('没有选择分卷');
    final option = PackOption.all(
      addChapterTitle: job['add_titles'] == true, selectedVolumes: selected);
    logger.i('option: $option, combineVolume: ${job['merge'] == true}');
    await core.pack(source: source, novel: novel, option: option,
        combineVolume: job['merge'] == true);
    stdout.writeln('BILI_GUI_JOB_DONE');
  } catch (e, stack) {
    stderr.writeln('下载失败: $e');
    logger.e('下载失败: $e', stackTrace: stack);
    exitCode = 1;
  } finally {
    await logger.close();
    await stdout.flush();
    await stderr.flush();
  }
}
