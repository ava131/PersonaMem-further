import json
import tempfile
import unittest
from pathlib import Path

from convert import build, choose_prefixes, common_prefix, event_text, parser


class CharacterTokenizer:
    all_special_ids = []

    def encode(self, text, add_special_tokens=False):
        return list(map(ord, text))

    def decode(self, ids, **kwargs):
        return ''.join(map(chr, ids))


class WorkloadTests(unittest.TestCase):
    def test_round_order_payload_length_and_no_annotation_leak(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for pid, letter in enumerate('XYZ'):
                folder = root / 'data' / 'backend' / str(pid)
                folder.mkdir(parents=True)
                event = {'source_timestamp': 1,
                         'conversation': [{'role': 'user', 'content': letter * 120}],
                         'preferences': [{'secret_annotation': 'DO_NOT_INCLUDE'}]}
                (folder / 'chatbot.json').write_text(json.dumps([event]))
            args = parser().parse_args([
                'build', '--data-dir', str(root / 'data'), '--output-dir', str(root / 'out'),
                '--rounds', '3', '--requests-per-round', '3', '--initial-tokens', '32',
                '--increment-tokens', '7', '--apps', 'chatbot', '--emit-token-ids'])
            manifest = build(args, CharacterTokenizer())
            self.assertEqual(manifest['total_requests'], 9)
            gsm = [json.loads(x) for x in (root / 'out' / 'gsm8k.jsonl').read_text().splitlines()]
            lb = [json.loads(x) for x in (root / 'out' / 'longbenchv2.jsonl').read_text().splitlines()]
            meta = [json.loads(x) for x in (root / 'out' / 'requests.meta.jsonl').read_text().splitlines()]
            for i, (g, l, m) in enumerate(zip(gsm, lb, meta)):
                self.assertEqual(g['question'], l['context'])
                self.assertEqual(len(g['question']), 32 + (i // 3) * 7)
                self.assertEqual(m['session_id'], i % 3)
                self.assertEqual(m['previous_line'], i - 2 if i >= 3 else None)
                self.assertNotIn('DO_NOT_INCLUDE', g['question'])
                if i >= 3:
                    self.assertTrue(g['question'].startswith(gsm[i - 3]['question']))
            self.assertEqual(manifest['first_round_shared_full_prefix_blocks'], 0)
            with self.assertRaisesRegex(ValueError, 'already exist'):
                build(args, CharacterTokenizer())

    def test_nonreversible_cut_is_rejected(self):
        import random

        class BrokenTokenizer(CharacterTokenizer):
            def decode(self, ids, **kwargs):
                return super().decode(ids) + '!'

        self.assertIsNone(choose_prefixes(BrokenTokenizer(), [65] * 100, [32, 40],
                                         [], 8, 10, random.Random(0)))

    def test_exact_prefix_overlap_and_insufficient_text(self):
        import random
        tok = CharacterTokenizer()
        self.assertEqual(common_prefix([1, 2, 3], [1, 2, 4]), 2)
        self.assertIsNone(choose_prefixes(tok, [65] * 100, [32, 40],
                                         [[65] * 32], 8, 10, random.Random(0)))
        self.assertIsNone(choose_prefixes(tok, [65] * 5, [32, 40],
                                         [], 8, 10, random.Random(0)))

    def test_content_selection(self):
        event = {'conversation': [{'role': 'user', 'content': 'hello'}],
                 'interaction_format': {'user_message': 'DUPLICATE'},
                 'preferences': [{'text': 'ANNOTATION'}]}
        self.assertEqual(event_text(event), 'user:\nhello')
        self.assertEqual(event_text({'preferences': [{'text': 'ANNOTATION'}]}), '')


if __name__ == '__main__':
    unittest.main()
