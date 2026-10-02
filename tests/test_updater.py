import unittest
from unittest.mock import Mock, patch
import requests
import updater


def response(code=200, data=None, text='', headers=None):
    value = Mock(status_code=code, text=text, content=text.encode(), headers=headers or {})
    value.json.return_value = data
    if code >= 400:
        value.raise_for_status.side_effect = requests.HTTPError(str(code))
    return value


class UpdateTests(unittest.TestCase):
    def setUp(self):
        updater._release_cache.clear()

    @patch('updater.request_get')
    def test_forbidden_is_not_rate_limit(self, get):
        get.side_effect = [response(403), requests.ConnectionError()]
        self.assertEqual(updater.check_target('a/b', '1')['status'], 'forbidden')

    @patch('updater.request_get')
    def test_limit_falls_back_to_feed(self, get):
        feed = '<feed xmlns="http://www.w3.org/2005/Atom"><entry><link href="https://github.com/a/b/releases/tag/v2.0"/></entry></feed>'
        get.side_effect = [response(403, headers={'X-RateLimit-Remaining': '0'}), response(text=feed)]
        result = updater.check_target('a/b', '1')
        self.assertEqual(result['status'], 'update')
        self.assertEqual(result['latest'], 'v2.0')
        self.assertEqual(updater.check_target('a/b', '2')['status'], 'latest')
        self.assertEqual(get.call_count, 2)

    @patch('updater.request_get')
    def test_no_release(self, get):
        get.side_effect = [response(404), response(data=[])]
        self.assertEqual(updater.check_target('a/b', '1')['status'], 'no_release')

    @patch('updater.request_get')
    def test_prerelease(self, get):
        get.side_effect = [response(404), response(data=[{'tag_name': 'v0.2.50', 'prerelease': True}])]
        self.assertEqual(updater.check_target('a/b', '0.2.49')['status'], 'update')

    @patch('updater.request_get')
    def test_rate_limit_reported_when_feed_also_fails(self, get):
        get.side_effect = [response(429), requests.ConnectionError()]
        self.assertEqual(updater.check_target('a/b', '1')['status'], 'ratelimit')
