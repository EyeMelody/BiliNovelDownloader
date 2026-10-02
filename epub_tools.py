"""Generate real simplified/traditional EPUBs without modifying source files."""
import logging
import zipfile
from pathlib import Path
from xml.dom import minidom
import opencc
from core import DIR_DOWNLOADS, DIR_SIMP, DIR_TRAD, sanitize_filename
from download_job import validate_epub

S2TW_CONVERTER = opencc.OpenCC('s2tw')
T2S_CONVERTER = opencc.OpenCC('t2s')


def convert_epub_with_opencc(input_epub, output_epub, converter, target_lang=None):
    input_epub, output_epub = Path(input_epub), Path(output_epub)
    validate_epub(input_epub)
    with zipfile.ZipFile(input_epub) as zin, zipfile.ZipFile(output_epub, 'w') as zout:
        zout.writestr('mimetype', b'application/epub+zip', compress_type=zipfile.ZIP_STORED)
        for item in zin.infolist():
            if item.filename == 'mimetype': continue
            data = zin.read(item.filename)
            if item.filename.lower().endswith(('.xhtml', '.html', '.opf', '.ncx')):
                doc = minidom.parseString(data)
                def walk(node):
                    if node.nodeType in (node.TEXT_NODE, node.CDATA_SECTION_NODE):
                        node.data = converter.convert(node.data)
                    if node.nodeType == node.ELEMENT_NODE:
                        for attr in ('alt', 'title', 'label'):
                            if node.hasAttribute(attr):
                                node.setAttribute(attr, converter.convert(node.getAttribute(attr)))
                        if target_lang:
                            for attr in ('lang', 'xml:lang'):
                                if node.hasAttribute(attr): node.setAttribute(attr, target_lang)
                    for child in node.childNodes: walk(child)
                    if target_lang and node.nodeType == node.ELEMENT_NODE and node.localName == 'language':
                        for child in node.childNodes:
                            if child.nodeType == child.TEXT_NODE: child.data = target_lang
                walk(doc)
                data = doc.toxml(encoding='utf-8')
            # Paths, href/src attributes and image bytes remain unchanged.
            zout.writestr(item.filename, data, compress_type=zipfile.ZIP_DEFLATED)
    validate_epub(output_epub)


def process_downloaded_folder(source_folder_path, base_path, logger=None):
    logger = logger or logging.getLogger(__name__)
    source = Path(source_folder_path)
    epubs = sorted(source.glob('*.epub'))
    if not epubs: raise ValueError('下载任务没有生成 EPUB。')
    for directory, converter, language in (
        (DIR_SIMP, T2S_CONVERTER, 'zh-CN'), (DIR_TRAD, S2TW_CONVERTER, 'zh-TW')
    ):
        target = Path(base_path) / DIR_DOWNLOADS / directory / sanitize_filename(converter.convert(source.name))
        target.mkdir(parents=True, exist_ok=True)
        for epub in epubs:
            dest = target / sanitize_filename(converter.convert(epub.name))
            pending = dest.with_suffix('.pending.epub')
            convert_epub_with_opencc(epub, pending, converter, language)
            pending.replace(dest)
            logger.info('已保存 %s：%s', directory, dest)
    return len(epubs)
