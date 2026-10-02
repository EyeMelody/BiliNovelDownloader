import json, sys, time, zipfile
from pathlib import Path

if '--capabilities' in sys.argv:
    print(json.dumps({'protocol': 1, 'http_proxy': True}))
    sys.exit(0)
job = json.loads(Path(sys.argv[2]).read_text(encoding='utf-8'))
Path('received.json').write_text(json.dumps(job), encoding='utf-8')
mode = job.get('test_mode', 'ok')
if mode == 'fail':
    print('intentional failure', flush=True); sys.exit(1)
if mode == 'stall':
    time.sleep(30); sys.exit(0)
def epub(path):
    with zipfile.ZipFile(path, 'w') as z:
        z.writestr('mimetype', 'application/epub+zip')
        z.writestr('META-INF/container.xml', '<container><rootfiles><rootfile full-path="OEBPS/content.opf"/></rootfiles></container>')
        z.writestr('OEBPS/content.opf', '<package xmlns:dc="http://purl.org/dc/elements/1.1/"><metadata><dc:title>測試書</dc:title><dc:language>zh-TW</dc:language></metadata><manifest><item id="c" href="繁體.xhtml"/></manifest><spine><itemref idref="c"/></spine></package>')
        z.writestr('OEBPS/繁體.xhtml', '<html><body><p>這是繁體測試</p><img src="圖.jpg"/></body></html>')
        z.writestr('OEBPS/圖.jpg', b'image-bytes')
if mode != 'empty':
    for n in (job.get('volumes') or [1,2])[:1] if job.get('merge') else (job.get('volumes') or [1,2]):
        epub(f'book-{n}.epub')
if mode != 'missing_marker': print('BILI_GUI_JOB_DONE', flush=True)
