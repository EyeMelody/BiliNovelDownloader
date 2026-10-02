import json, os, sys, tempfile, threading, unittest, zipfile
from pathlib import Path
from unittest.mock import patch
from download_job import run_job, DownloadError, parse_volumes
from network import validate_proxy, make_session, save_settings, load_settings
from core import normalize_novel_url
from epub_tools import convert_epub_with_opencc, T2S_CONVERTER

ROOT=Path(__file__).resolve().parent.parent

class DownloadTests(unittest.TestCase):
    def setUp(self):
        run_root=ROOT/'.test-runs'; run_root.mkdir(exist_ok=True)
        self.work=Path(tempfile.mkdtemp(dir=run_root))
        self.command=[sys.executable,str(ROOT/'tests/fake_core.py')]
        self.job={'url':'https://www.bilinovel.com/novel/4325.html','volumes':[1],
                  'merge':False,'add_titles':True,'proxy':None}

    def run_core(self, **changes):
        job=dict(self.job, **changes)
        return run_job(self.command,self.work,job,threading.Event(),stall_seconds=.5,timeout_seconds=4)

    def test_single_volume_title_flag_not_shifted(self):
        self.assertEqual(len(self.run_core()),1)
        received=json.loads((self.work/'received.json').read_text())
        self.assertIs(received['add_titles'],True)
        self.assertIs(received['merge'],False)

    def test_multi_volume(self):
        self.assertEqual(len(self.run_core(volumes=[1,3])),2)

    def test_merged_volume(self):
        self.assertEqual(len(self.run_core(volumes=[1,3],merge=True)),1)

    def test_stall_still_detected(self):
        with self.assertRaises(DownloadError) as e:self.run_core(test_mode='stall')
        self.assertEqual(e.exception.reason,'stall')

    def test_failed_core_not_success(self):
        with self.assertRaises(DownloadError):self.run_core(test_mode='fail')

    def test_completion_marker_and_output_required(self):
        with self.assertRaises(DownloadError):self.run_core(test_mode='missing_marker')

    def test_no_output_not_success(self):
        with self.assertRaises(DownloadError):self.run_core(test_mode='empty')

    def test_cancellation(self):
        event=threading.Event(); event.set()
        with self.assertRaises(DownloadError) as e:
            run_job(self.command,self.work,dict(self.job,test_mode='stall'),event)
        self.assertEqual(e.exception.reason,'cancelled')

    def test_range_validation(self):
        self.assertEqual(parse_volumes('1,3-5,3'),[1,3,4,5])
        self.assertIsNone(parse_volumes('0'))
        for value in ('-1','0,1','4-2','abc','1;2'):
            with self.assertRaises(ValueError):parse_volumes(value)

    def test_proxy_propagates_without_env_override(self):
        settings={'proxy_enabled':True,'proxy_url':'http://127.0.0.1:7890'}
        save_settings(settings,self.work/'settings.json')
        self.assertEqual(load_settings(self.work/'settings.json'),settings)
        with patch.dict(os.environ,{'HTTPS_PROXY':'http://wrong:99'}):
            with make_session(settings) as session:
                self.assertFalse(session.trust_env)
                self.assertEqual(session.proxies['https'],settings['proxy_url'])
            with make_session(dict(settings,proxy_enabled=False)) as session:
                self.assertEqual(session.proxies,{})
                self.assertFalse(session.trust_env)
        self.run_core(proxy=settings['proxy_url'])
        self.assertEqual(json.loads((self.work/'received.json').read_text())['proxy'],settings['proxy_url'])

    def test_proxy_validation(self):
        self.assertEqual(validate_proxy('127.0.0.1:7890'),'http://127.0.0.1:7890')
        for url in ('socks5://localhost:7890','http://user:pass@localhost:7890','http://localhost:0','http://localhost:7890/path'):
            with self.assertRaises(ValueError):validate_proxy(url)

    def test_url_normalization(self):
        for value in ('4325','https://tw.linovelib.com/novel/4325.html','https://www.linovelib.com/novel/4325.html'):
            self.assertEqual(normalize_novel_url(value),self.job['url'])
        with self.assertRaises(ValueError):normalize_novel_url('https://evil.example/novel/4325.html')

    def test_simplified_text_preserves_resource_paths_and_images(self):
        source=self.run_core()[0]; result=self.work/'simplified.epub'
        convert_epub_with_opencc(source,result,T2S_CONVERTER,'zh-CN')
        with zipfile.ZipFile(result) as z:
            self.assertIn('这是繁体测试',z.read('OEBPS/繁體.xhtml').decode())
            self.assertIn('src="圖.jpg"',z.read('OEBPS/繁體.xhtml').decode())
            self.assertEqual(z.read('OEBPS/圖.jpg'),b'image-bytes')
            self.assertIn('zh-CN',z.read('OEBPS/content.opf').decode())
            self.assertEqual(z.infolist()[0].filename,'mimetype')
            self.assertEqual(z.infolist()[0].compress_type,zipfile.ZIP_STORED)

if __name__=='__main__':unittest.main()
