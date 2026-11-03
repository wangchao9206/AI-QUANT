"""Verify the shipped reading corpus independently of the browser renderer."""
import hashlib
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CATALOG = json.loads((ROOT / 'frontend/src/content/chanlunChapters.json').read_text(encoding='utf-8'))
FOLDER = ROOT / 'frontend/public/reading-assets/chanlun' / CATALOG['version']


class ChanlunBookTests(unittest.TestCase):
    def test_all_108_courses_and_images_match_recorded_hashes(self):
        self.assertEqual({c['number'] for c in CATALOG['chapters']}, set(range(1, 109)))
        provenance = json.loads((FOLDER / 'provenance.json').read_text(encoding='utf-8'))
        for name, checksum in provenance['assetSha256'].items():
            with self.subTest(asset=name):
                self.assertEqual(hashlib.sha256((FOLDER / name).read_bytes()).hexdigest(), checksum)
        for item in CATALOG['chapters']:
            data = json.loads((FOLDER / f"chapter-{item['number']:03d}.json").read_text(encoding='utf-8'))
            self.assertEqual(data['number'], item['number'])
            self.assertEqual(data['author'], '缠中说禅')
            self.assertGreater(data['textLength'], 100)
            self.assertNotIn('本文评论获取', json.dumps(data['blocks'], ensure_ascii=False))
            for block in data['blocks']:
                if block['type'] == 'image':
                    self.assertTrue(block['src'].startswith(f"/reading-assets/chanlun/{CATALOG['version']}/images/"))
                    self.assertTrue((ROOT / 'frontend/public' / block['src'].lstrip('/')).is_file())

    def test_reprint_permission_and_archive_license_are_preserved(self):
        provenance = json.loads((FOLDER / 'provenance.json').read_text(encoding='utf-8'))
        self.assertEqual([p['course'] for p in provenance['authorPermissions']], [8, 17])
        self.assertIn('注明出处', provenance['authorPermissions'][0]['record'])
        self.assertIn('推广一下本博客', provenance['authorPermissions'][1]['record'])
        self.assertIn('MIT License', (FOLDER / 'LICENSE.txt').read_text(encoding='utf-8'))
        self.assertIn('原文作者：缠中说禅', (FOLDER / 'NOTICE.txt').read_text(encoding='utf-8'))


if __name__ == '__main__':
    unittest.main()
