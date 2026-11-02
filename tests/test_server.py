import sys, unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import server

class CoreTests(unittest.TestCase):
    def test_url_validation(self):
        for url in ('http://localhost/', 'http://127.0.0.1/', 'http://10.0.0.1/', 'file:///etc/passwd', 'https://example.com:8080/', 'https://user:pass@example.com/'):
            with self.subTest(url=url), self.assertRaises(ValueError): server.normalize(url)
        self.assertEqual(server.normalize('https://example.com/#hi'), 'https://example.com/')
    def test_reject_private_dns(self):
        with patch('server.socket.getaddrinfo',return_value=[(2,1,6,'',('10.0.0.1',443))]):
            with self.assertRaisesRegex(ValueError,'non-public'): server.fetch('https://example.com/')
    def test_robots_and_extraction(self):
        def fetch(url):
            if url.endswith('/robots.txt'): return (200,'text/plain','User-agent: *\nDisallow: /private')
            if url.endswith('/'): return (200,'text/html','''<title>Acme</title><script type="application/ld+json">{"@type":"Person","name":"Ada Example","jobTitle":"Founder","email":"ada@example.com"}</script><a href="/private">Private</a><a href="/contact">Contact</a>''')
            if url.endswith('/contact'): return (200,'text/html','<a href="mailto:team@example.com">Contact</a>')
            self.fail('unexpected URL '+url)
        with patch('server.fetch',side_effect=fetch), patch('server.time.sleep'):
            result=server.crawl('https://example.com/',3)
        self.assertEqual(result['pagesScanned'],2)
        self.assertTrue(any(x['name']=='Ada Example' and x['role']=='Founder' for x in result['results']))
        self.assertTrue(any(x['email']=='team@example.com' and not x['name'] for x in result['results']))
        self.assertTrue(result['warnings'])
    def test_conservative_robots_wildcard_and_precedence(self):
        rules='User-agent: *\nAllow: /\nDisallow: /private*\n'
        self.assertTrue(server.conservative_disallows(rules, 'https://example.com/private/contact'))
        self.assertTrue(server.conservative_disallows(rules, 'https://example.com/%70rivate/contact'))
        self.assertFalse(server.conservative_disallows(rules, 'https://example.com/public'))
    def test_robots_failure_closed(self):
        with patch('server.fetch',return_value=(503,'text/plain','')):
            with self.assertRaisesRegex(ValueError,'robots.txt'): server.crawl('https://example.com/')
    def test_person_requires_contact(self):
        self.assertEqual(server.people_json({'@type':'Person','name':'No contact'},'https://example.com'),[])
if __name__ == '__main__': unittest.main()
