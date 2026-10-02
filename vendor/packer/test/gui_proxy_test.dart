import 'dart:io';
import 'package:dio/dio.dart';
import 'package:test/test.dart';
import 'package:bili_novel_packer/gui_proxy.dart';

void main() {
  test('independent text and image clients use the configured proxy', () async {
    final proxy = await HttpServer.bind(InternetAddress.loopbackIPv4, 0);
    final paths = <String>[];
    proxy.listen((request) async {
      paths.add(request.uri.toString());
      request.response.write('proxied');
      await request.response.close();
    });
    HttpOverrides.global = GuiProxyOverrides('127.0.0.1:${proxy.port}');
    final text = Dio();
    final images = Dio();
    try {
      expect((await text.get('http://text.invalid/chapter')).data, 'proxied');
      expect((await images.get<List<int>>('http://images.invalid/cover.jpg',
          options: Options(responseType: ResponseType.bytes))).data, isNotEmpty);
      expect(paths.length, 2);
      expect(paths.first, contains('text.invalid'));
      expect(paths.last, contains('images.invalid'));
    } finally {
      text.close(force: true); images.close(force: true);
      HttpOverrides.global = null;
      await proxy.close(force: true);
    }
  });
  test('reject unsupported proxy schemes and credentials', () {
    expect(parseGuiProxy('http://127.0.0.1:7890'), '127.0.0.1:7890');
    expect(parseGuiProxy(null), isNull);
    expect(() => parseGuiProxy('socks5://127.0.0.1:7890'), throwsFormatException);
    expect(() => parseGuiProxy('http://user:pass@localhost:7890'), throwsFormatException);
  });
}
