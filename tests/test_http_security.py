import unittest,threading,http.client
from http.server import ThreadingHTTPServer
from api.index import handler
class HTTPTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.server=ThreadingHTTPServer(('127.0.0.1',0),handler)
  cls.thread=threading.Thread(target=cls.server.serve_forever,daemon=True);cls.thread.start()
 @classmethod
 def tearDownClass(cls):cls.server.shutdown();cls.server.server_close();cls.thread.join()
 def get(self,path):
  c=http.client.HTTPConnection('127.0.0.1',self.server.server_port);c.request('GET',path);r=c.getresponse();out=(r.status,dict(r.getheaders()),r.read());c.close();return out
 def test_private_and_unknown_paths_are_not_pages(self):
  for p in ['/.env','/_env','/.git/config','/api/.env','/work','/database/src/gim_db/repository.py']:
   with self.subTest(path=p):self.assertEqual(self.get(p)[0],404)
 def test_http_headers_restrict_embedding_and_type_sniffing(self):
  status,h,_=self.get('/');self.assertEqual(status,200)
  self.assertEqual(h.get('X-Content-Type-Options'),'nosniff')
  self.assertIn("frame-ancestors 'none'",h.get('Content-Security-Policy',''))
  self.assertEqual(h.get('Referrer-Policy'),'no-referrer')
