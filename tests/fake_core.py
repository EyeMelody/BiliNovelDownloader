import json, sys, time, zipfile
from pathlib import Path
sys.stdout.reconfigure(encoding='utf-8')
sys.stdin.reconfigure(encoding='utf-8')
mode = sys.argv[1] if len(sys.argv) > 1 else 'ok'
def prompt(text):
    # Deliberately split non-newline prompts into multiple pipe writes.
    for chunk in (text[:5], text[5:]):
        sys.stdout.write(chunk); sys.stdout.flush()
    return input()
url = prompt('请输入链接(多个链接使用空格隔开):')
if mode == 'fail':
    print('运行出错.(0.2.49)', flush=True)
    prompt('请输入链接(多个链接使用空格隔开):')
    sys.exit(1)
if mode == 'stall':
    time.sleep(30); sys.exit(0)
print('[1] 第一卷\n[2] 第二卷\n[3] 第三卷\n[0] 选择全部', flush=True)
selection = prompt('请选择要下载的分卷: ')
volumes = [1,2,3] if selection == '0' else [int(x) for x in selection.split(',')]
merge = len(volumes) > 1 and prompt('是否合并选择的分卷为一个文件? ') == '1'
titles = prompt('是否在每章开头添加章节标题? ') == '1'
Path('received.json').write_text(json.dumps({'url':url,'volumes':volumes,'merge':merge,'add_titles':titles}), encoding='utf-8')
def epub(path):
    with zipfile.ZipFile(path, 'w') as z:
        z.writestr('mimetype', 'application/epub+zip')
        z.writestr('META-INF/container.xml', '<container><rootfiles><rootfile full-path="OEBPS/content.opf"/></rootfiles></container>')
        z.writestr('OEBPS/content.opf', '<package xmlns:dc="http://purl.org/dc/elements/1.1/"><metadata><dc:title>測試書</dc:title><dc:language>zh-TW</dc:language></metadata><manifest><item id="c" href="繁體.xhtml"/></manifest><spine><itemref idref="c"/></spine></package>')
        z.writestr('OEBPS/繁體.xhtml', '<html><body><p>這是繁體測試</p><img src="圖.jpg"/></body></html>')
        z.writestr('OEBPS/圖.jpg', b'image-bytes')
if mode != 'empty':
    targets = volumes[:1] if merge else volumes
    for n in targets:
        epub(f'book-{n}.epub')
        if mode != 'missing_marker':
            print(f'打包完成: book-{n}.epub', flush=True)
        if mode == 'partial': break
if mode == 'exit_after_file': sys.exit(0)
prompt('请输入链接(多个链接使用空格隔开):')
