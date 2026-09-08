"""Full-model viewer search, ranking and local HTTP boundary."""
import gzip
from http.client import HTTPConnection
import json
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_similarity import fixture
from similarity import fit, write_model
from similarity_viewer import ModelIndex, handler_for


class ViewerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory = tempfile.TemporaryDirectory()
        root = Path(cls.directory.name)
        data = fixture()
        data['tags'].append({'id': 7, 'name': 'Brassy sound', 'type': 'keyword', 'emoji': None})
        data['event_tags'].append({'event_id': 2, 'tag_id': 7})
        write_model(data, fit(data, dimensions=6, min_df=1), root / 'public', root)
        with gzip.open(root / 'snapshot.json.gz', 'wt', encoding='utf-8') as f:
            json.dump(data, f)
        cls.model = ModelIndex(root)

    @classmethod
    def tearDownClass(cls):
        cls.directory.cleanup()

    def test_search_exact_priority_type_pagination_and_historical_seed(self):
        model = self.model
        self.assertEqual(model.search('Jazz')['items'][0]['key'], 'tag:2')
        self.assertEqual(model.search('Jazz', 'event')['total'], 2)
        self.assertEqual(model.search('Jazz', 'event', offset=1, limit=1)['items'][0]['key'], 'event:2')
        self.assertEqual(model.search('Brassy', 'keyword')['total'], 1)
        self.assertEqual(model.search('Brassy', 'tag')['total'], 0)
        self.assertTrue(model.detail('event:1')['archived'])
        self.assertNotIn('event:5', model.positions)  # suppressed listing

    def test_similarity_is_sorted_excludes_self_and_crosses_types(self):
        result = self.model.neighbors('tag:2', events='all', tags='all')
        events = result['groups']['event']['items']
        self.assertEqual({e['id'] for e in events[:2]}, {1, 2})
        self.assertEqual([e['score'] for e in events], sorted([e['score'] for e in events], reverse=True))
        self.assertNotIn('tag:2', [e['key'] for e in result['groups']['tag']['items']])
        self.assertEqual(result['groups']['place']['items'][0]['key'], 'place:1')

    def test_filters_limits_and_browser_precision(self):
        active = self.model.neighbors('tag:2', limit=1)
        self.assertEqual(len(active['groups']['event']['items']), 1)
        self.assertEqual(active['groups']['event']['items'][0]['key'], 'event:2')
        history = self.model.neighbors('tag:2', events='history', tags='keywords')
        self.assertEqual([e['key'] for e in history['groups']['event']['items']], ['event:1'])
        self.assertEqual([e['key'] for e in history['groups']['tag']['items']], ['tag:7'])
        browser = self.model.neighbors('tag:2', precision='browser')['groups']['event']['items'][0]
        self.assertAlmostEqual(browser['score'], active['groups']['event']['items'][0]['score'], delta=.02)

    def test_zero_vectors_and_invalid_inputs(self):
        zero = self.model.neighbors('tag:4')
        self.assertFalse(zero['seed']['hasVector'])
        self.assertTrue(all(g['total'] == 0 for g in zero['groups'].values()))
        with self.assertRaises(KeyError):
            self.model.neighbors('event:999')
        with self.assertRaises(ValueError):
            self.model.neighbors('tag:2', minimum=float('nan'))

    def test_http_serves_only_viewer_assets_and_readonly_api(self):
        server = ThreadingHTTPServer(('127.0.0.1', 0), handler_for(self.model))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            def request(path, host=None):
                conn = HTTPConnection('127.0.0.1', server.server_port)
                conn.request('GET', path, headers={'Host': host} if host else {})
                response = conn.getresponse()
                result = response.status, response.read()
                conn.close()
                return result
            self.assertEqual(request('/')[0], 200)
            status, body = request('/api/neighbors?entity=tag:2&limit=100')
            self.assertEqual(status, 200)
            self.assertEqual(json.loads(body)['seed']['name'], 'Jazz')
            self.assertEqual(request('/api/meta', host='untrusted.example')[0], 403)
            self.assertEqual(request('/snapshot.json.gz')[0], 404)
            self.assertEqual(request('/../similarity.py')[0], 404)
            self.assertEqual(request('/api/neighbors?entity=tag:2&minimum=oops')[0], 400)
        finally:
            server.shutdown()
            server.server_close()
            thread.join()


if __name__ == '__main__':
    unittest.main()
