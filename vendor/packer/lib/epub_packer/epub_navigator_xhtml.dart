import 'package:bili_novel_packer/epub_packer/epub_navigator_ncx.dart';
import 'package:bili_novel_packer/epub_packer/epub_node.dart';
import 'package:xml/xml.dart';

/// toc.ncx
class EpubNavigatorXHtml implements EpubNode {
  final XmlBuilder _builder = XmlBuilder();

  final List<NavPoint> _navPointList = [];

  void addNavPoint(NavPoint navPoint) {
    _navPointList.add(navPoint);
  }

  EpubNavigatorXHtml() {
    _builder.declaration(
      encoding: "UTF-8",
      attributes: {
        "standalone": "no",
      },
    );
  }

  @override
  XmlNode build() {
    _builder.element(
      "html",
      attributes: {
        "xmlns": "http://www.w3.org/1999/xhtml",
        "xmlns:epub": "http://www.idpf.org/2007/ops",
        "xml:lang": "zh",
      },
      nest: () {
        _buildHead();
        _buildBody();
      },
    );
    return _builder.buildDocument();
  }

  void _buildHead() {
    _builder.element(
      "head",
      nest: () {
        _builder.element(
          "meta",
          attributes: {
            "charset": "UTF-8",
          },
        );
        _builder.element("title", nest: "目录");
      },
    );
  }

  void _buildBody() {
    _builder.element(
      "body",
      nest: () {
        _builder.element(
          "nav",
          attributes: {
            "id": "toc",
            "role": "doc-toc",
            "epub:type": "toc",
          },
          nest: () {
            _builder.element("h1", nest: "目录");
            _buildNav(_navPointList);
          },
        );
      },
    );
  }

  void _buildNav(List<NavPoint> navPoints) {
    _builder.element(
      "ol",
      nest: () {
        for (int i = 0; i < navPoints.length; i++) {
          _buildNavItem(navPoints[i], navPoints[0].src!);
        }
      },
    );
  }

  void _buildNavItem(NavPoint navPoint, String href) {
    _builder.element(
      "li",
      nest: () {
        _builder.element(
          "a",
          attributes: {
            "href": navPoint.src ?? href,
          },
          nest: navPoint.title,
        );
        if (navPoint.children.isNotEmpty) {
          _buildNav(navPoint.children);
        }
      },
    );
  }
}
