import unittest
from scripts.migrate_frozen_sources import digest, source_rows


class SourcePreservationTests(unittest.TestCase):
    def test_duplicate_legacy_ids_remain_distinct_source_rows(self):
        source = {'rows': [{'row': 1, 'values': ['Task ID', 'Value']},
                           {'row': 2, 'values': ['DUPLICATE', 'first']},
                           {'row': 7, 'values': ['DUPLICATE', 'second']}]}
        rows = list(source_rows(source))
        self.assertEqual([r[0] for r in rows], ['row:2', 'row:7'])
        self.assertNotEqual(rows[0][2], rows[1][2])
        self.assertEqual(rows[1][1]['values'], ['DUPLICATE', 'second'])
        self.assertEqual(rows[1][1]['source_architecture'], '1X')

    def test_repeated_source_locator_is_rejected(self):
        with self.assertRaisesRegex(ValueError, 'invalid_source_row_identity'):
            list(source_rows({'rows': [{'row': 2, 'values': ['one']},
                                      {'row': 2, 'values': ['two']}]}))

    def test_content_verification_detects_whitespace_and_value_changes(self):
        original = {'values': [' keep whitespace ', None, 0]}
        self.assertNotEqual(digest(original), digest({'values': ['keep whitespace', None, 0]}))
        self.assertNotEqual(digest(original), digest({'values': [' keep whitespace ', None, '0']}))


if __name__ == '__main__':
    unittest.main()
