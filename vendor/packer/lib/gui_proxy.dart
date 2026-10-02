import 'dart:io';

/// One explicit policy shared by every Dio client (text, images and scripts).
class GuiProxyOverrides extends HttpOverrides {
  final String? proxy;
  GuiProxyOverrides(this.proxy);

  @override
  HttpClient createHttpClient(SecurityContext? context) {
    final client = super.createHttpClient(context);
    client.findProxy = (_) => proxy == null ? 'DIRECT' : 'PROXY $proxy';
    client.connectionTimeout = const Duration(seconds: 30);
    return client;
  }
}

String? parseGuiProxy(Object? value) {
  if (value == null || value == '') return null;
  final uri = Uri.parse(value as String);
  if (uri.scheme != 'http' || uri.host.isEmpty || !uri.hasPort ||
      uri.port < 1 || uri.port > 65535 || uri.userInfo.isNotEmpty ||
      (uri.path.isNotEmpty && uri.path != '/') || uri.hasQuery || uri.hasFragment) {
    throw const FormatException('代理必须为 http://主机:端口');
  }
  return '${uri.host.contains(':') ? '[${uri.host}]' : uri.host}:${uri.port}';
}
