"""Synthetic recheck integrity tests; no changes to real human annotations."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from semantic_human_recheck import (
    flags_for, join_human, queue_frames, summarize, render_ui, prepare,
    TEMPLATE, SCHEMA, digest, write_json,
)


def human(key, label='hand', cover='bare', visibility='full'):
    return {'id': key, 'label': label, 'cover': cover if label == 'hand' else None,
            'visibility': visibility if label == 'hand' else None, 'note': '',
            'reviewed_at': '2026-09-24T21:00:00Z'}


def auto(key, presence='hand', prediction='HUMAN', cover='bare', visibility='full'):
    return {'id': key, 'reference': {'presence': presence, 'cover': cover,
                                   'visibility': visibility, 'image_sha256': 'synthetic'},
            'monitor': {'prediction': prediction, 'image_sha256': 'synthetic'}}


class RecheckTests(unittest.TestCase):
    def fixture(self):
        labels = [human('c0', 'no_hand'), human('c1', visibility='uncertain'),
                  human('c2', 'uncertain'), human('c3'), human('c4', cover='glove'),
                  human('c5', 'no_hand')]
        models = [auto('o0'), auto('o1', visibility='partial'), auto('o2'),
                  auto('o3', visibility='partial'), auto('o4'), auto('o5', presence='no_hand', prediction='OBJECT')]
        frames = [{'case_id': f'c{i}', 'original_id': f'o{i}', 'image_sha256': 'synthetic',
                   'image': f'../../semantic_audit/frames/{i}.jpg',
                   'inclusion_weight': 2 if i == 5 else 1, 'stratum': 'test'} for i in range(6)]
        payload = {'labels': labels, 'prior_model_exposure': 'no'}
        return {'frames': frames}, payload, models

    def test_flags_do_not_treat_model_as_truth(self):
        h = human('case', 'no_hand')
        before = deepcopy(h)
        self.assertEqual(flags_for(h, auto('frame')), ['human_vs_reference_presence', 'human_vs_monitor_presence'])
        self.assertEqual(h, before)
        # Disagreement must not replace the human label, even if both models agree.
        self.assertEqual(h['label'], 'no_hand')

    def test_uncertainty_not_coerced_to_negative_or_condition_mismatch(self):
        self.assertEqual(flags_for(human('x', 'uncertain'), auto('x')), ['human_presence_uncertain'])
        self.assertEqual(flags_for(human('x', cover='uncertain', visibility='uncertain'), auto('x')),
                         ['human_condition_uncertain'])
        self.assertEqual(flags_for(human('x'), auto('x', cover='unspecified')), [])
        self.assertEqual(flags_for(human('x'), auto('x', presence='error', prediction='ERROR', cover=None, visibility=None)), [])

    def test_unique_union_priority_and_nonmutation(self):
        manifest, payload, models = self.fixture()
        before = deepcopy((manifest, payload, models))
        joined = join_human(manifest, payload, models)
        frames = queue_frames(joined)
        self.assertEqual([r['case_id'] for r in frames], ['c2', 'c1', 'c0', 'c3', 'c4'])
        self.assertEqual(len({r['case_id'] for r in frames}), 5)
        self.assertEqual(frames[2]['flag_codes'], ['human_vs_reference_presence', 'human_vs_monitor_presence'])
        self.assertEqual((manifest, payload, models), before)
        self.assertTrue(all('human' not in r and 'automatic' not in r for r in frames))

    def test_summary_preserves_uncertain_and_distinguishes_weights(self):
        manifest, payload, models = self.fixture()
        result = summarize(join_human(manifest, payload, models), payload)
        self.assertEqual(result['original_human_counts'], {'no_hand': 2, 'hand': 3, 'uncertain': 1})
        self.assertEqual(result['original_human_metadata']['prior_model_exposure'], 'no')
        raw = result['raw_unweighted_tables']['monitor']
        weighted = result['weighted_finite_population_counts']['tables']['monitor']
        self.assertEqual(raw['uncertain']['HUMAN'], 1)
        self.assertEqual(raw['no_hand']['OBJECT'], 1)
        self.assertEqual(weighted['no_hand']['OBJECT'], 2)
        self.assertEqual(result['recheck_unique_count'], 5)

    def test_duplicate_missing_and_image_mismatch_rejected(self):
        for mode in ('duplicate', 'missing', 'image'):
            manifest, payload, models = self.fixture()
            if mode == 'duplicate':
                payload['labels'].append(deepcopy(payload['labels'][0]))
            elif mode == 'missing':
                payload['labels'].pop()
            else:
                models[0]['reference']['image_sha256'] = 'tampered'
            with self.subTest(mode=mode), self.assertRaises(ValueError):
                join_human(manifest, payload, models)

    def test_ui_no_answers_and_separate_storage(self):
        manifest, payload, models = self.fixture()
        frames = queue_frames(join_human(manifest, payload, models))
        html, ui = render_ui(TEMPLATE.read_text(), frames, 'newhash')
        self.assertTrue(all(set(r) == {'id', 'image'} for r in ui))
        self.assertIn("const key='aegis-human-recheck-'", html)
        self.assertIn("a.download='human_recheck_115_'", html)
        self.assertIn('labels={}', html)
        self.assertNotIn('flag_codes', html)
        self.assertNotIn('original_display_index', html)
        self.assertNotIn('human_vs_monitor_presence', html)
        self.assertNotIn('__FRAME_DATA__', html)

    def test_existing_destination_never_overwritten(self):
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp)
            sentinel = dest / 'original.txt'
            sentinel.write_text('untouched')
            with self.assertRaisesRegex(ValueError, 'Refusing to overwrite'):
                prepare(dest=dest)
            self.assertEqual(sentinel.read_text(), 'untouched')

    def test_generated_copy_and_original_preservation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / 'human.json'
            original_path = root / 'manifest.json'
            autos = root / 'auto'
            autos.mkdir()
            (autos / 'spec.json').write_text('{}')
            manifest, payload, models = self.fixture()
            payload.update(schema_version=SCHEMA, label_source='human', annotator='synthetic',
                           saved_at='2026-09-24T21:00:00Z')
            manifest['provenance'] = {'automatic_audit_hashes': {'spec.json': digest(autos / 'spec.json')}}
            write_json(original_path, manifest)
            payload['review_manifest_sha256'] = digest(original_path)
            # Preserve unusual whitespace as exact bytes, not only equivalent JSON.
            source.write_text(json.dumps(payload, indent=3) + '\n\n')
            before = {p: p.read_bytes() for p in (source, original_path, autos / 'spec.json')}
            dest = root / 'derived'
            with patch('semantic_human_recheck.validate_export', return_value={'valid': True, 'complete': True}), \
                 patch('semantic_human_recheck.load_run', return_value=({}, models)):
                result = prepare(source, original_path, autos, dest, TEMPLATE, expected_count=5)
            self.assertEqual(result['count'], 5)
            self.assertEqual((dest / 'original_human_export.json').read_bytes(), before[source])
            for path, original in before.items():
                self.assertEqual(path.read_bytes(), original)
            generated = json.loads((dest / 'manifest.json').read_text())
            self.assertEqual(generated['provenance']['original_human_export_sha256'], digest(source))
            self.assertFalse((dest / 'labels.json').exists())


if __name__ == '__main__':
    unittest.main()
