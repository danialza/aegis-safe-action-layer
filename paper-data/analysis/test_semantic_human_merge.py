"""Synthetic end-to-end tests; never read or write genuine annotations."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest

from semantic_auto_report import digest, read_json
from semantic_human_merge import AUTO_FILES, SCHEMA, merge
from semantic_human_review import SCHEMA as EXPORT_SCHEMA, write_json


def human(key, label='hand', cover='bare', visibility='full'):
    return {'id': key, 'label': label, 'cover': cover if label == 'hand' else None,
            'visibility': visibility if label == 'hand' else None, 'note': '',
            'reviewed_at': '2026-09-24T21:00:00Z'}


class MergeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.auto = self.root / 'semantic_auto_audit/run'
        self.auto.mkdir(parents=True)
        images = self.root / 'semantic_audit/frames'
        images.mkdir(parents=True)
        mapping = []
        for i in range(7):
            image = images / f'{i}.jpg'
            image.write_bytes(f'synthetic image {i}'.encode())
            mapping.append({'id': f'o{i}', 'image': f'frames/{i}.jpg', 'sha256': digest(image),
                            'run': 'r1' if i < 3 else 'r2', 'campaign': 'synthetic',
                            'frame_index': i, 'container_time_s': float(i)})
        write_json(self.auto / 'frame_mapping.json', mapping)
        write_json(self.auto / 'spec.json', {'total_frames': 7, 'mapping_sha256': digest(self.auto / 'frame_mapping.json')})
        spec_hash = digest(self.auto / 'spec.json')
        refs, mons = [], []
        for i, frame in enumerate(mapping):
            presence = 'hand' if i in (0, 2) else 'no_hand'
            base = {'id': frame['id'], 'spec_sha256': spec_hash, 'image_sha256': frame['sha256']}
            refs.append(dict(base, label_source='model', presence=presence,
                             code='B0' if presence == 'hand' else 'N',
                             cover='bare' if presence == 'hand' else None,
                             visibility='full' if presence == 'hand' else None))
            mons.append(dict(base, prediction='HUMAN' if i in (1, 2) else 'OBJECT'))
        for role, rows in (('reference', refs), ('monitor', mons)):
            (self.auto / f'{role}.jsonl').write_text(''.join(json.dumps(r) + '\n' for r in rows))
            write_json(self.auto / f'{role}.sealed.json', {'spec_sha256': spec_hash, 'rows': 7,
                       'predictions_sha256': digest(self.auto / f'{role}.jsonl')})
            write_json(self.auto / f'{role}_checkpoint.json', {'synthetic': True})
        write_json(self.auto / 'summary.json', {'synthetic': True})
        frames = []
        for i, frame in enumerate(mapping[:5]):
            stratum = 'disagreement' if i < 2 else 'both_positive' if i == 2 else 'both_negative'
            frames.append({'case_id': f'c{i}', 'original_id': frame['id'],
                           'image': '../../semantic_audit/' + frame['image'],
                           'image_sha256': frame['sha256'], 'run': frame['run'],
                           'campaign': frame['campaign'], 'frame_index': i, 'container_time_s': float(i),
                           'stratum': stratum, 'inclusion_probability': 0.5 if i >= 3 else 1,
                           'inclusion_weight': 2 if i >= 3 else 1})
        auto_hashes = {name: digest(self.auto / name) for name in AUTO_FILES}
        self.om = {'schema_version': EXPORT_SCHEMA, 'frames': frames,
                   'sampling': {'population_size': 7, 'sample_size': 5,
                                'population_counts': {'disagreement': 2, 'both_positive': 1, 'both_negative': 4},
                                'sample_counts': {'disagreement': 2, 'both_positive': 1, 'both_negative': 2}},
                   'provenance': {'automatic_audit_hashes': auto_hashes}}
        self.rm = {'schema_version': EXPORT_SCHEMA, 'frames': deepcopy(frames[:4]),
                   'provenance': {'automatic_audit_hashes': deepcopy(auto_hashes)},
                   'selection': {'count': 4, 'original_sample_size': 5}}
        self.op = {'schema_version': EXPORT_SCHEMA, 'label_source': 'human',
                   'annotator': 'Synthetic reviewer', 'prior_model_exposure': 'no',
                   'saved_at': '2026-09-24T21:01:00Z',
                   'labels': [human('c0'), human('c1', 'no_hand'), human('c2'),
                              human('c3', 'no_hand'), human('c4', 'uncertain')]}
        self.rp = dict(deepcopy(self.op), annotator='Synthetic reviewer 2', saved_at='2026-09-25T01:01:00Z')
        self.rp['labels'] = [human('c0', 'no_hand'), human('c1', 'uncertain'),
                             human('c2', cover='glove', visibility='partial'), human('c3', 'no_hand')]
        self.rp['labels'][2]['note'] = 'synthetic revision'
        for row in self.rp['labels']:
            row['reviewed_at'] = '2026-09-25T01:00:00Z'
        self.original_manifest = self.root / 'semantic_human_review/original/manifest.json'
        self.recheck_manifest = self.root / 'semantic_human_review/recheck/manifest.json'
        self.original_manifest.parent.mkdir(parents=True)
        self.recheck_manifest.parent.mkdir(parents=True)
        self.original = self.root / 'original.json'
        self.recheck = self.root / 'recheck.json'
        self.out = self.root / 'derived'
        self.sync()

    def tearDown(self):
        self.temp.cleanup()

    def sync(self):
        write_json(self.original_manifest, self.om)
        self.op['review_manifest_sha256'] = digest(self.original_manifest)
        # Deliberately noncanonical whitespace verifies byte-preserving copies.
        self.original.write_text(json.dumps(self.op, indent=3) + '\n\n')
        self.rm['provenance'].update(original_human_export_sha256=digest(self.original),
                                     original_sample_manifest_sha256=digest(self.original_manifest))
        write_json(self.recheck_manifest, self.rm)
        self.rp['review_manifest_sha256'] = digest(self.recheck_manifest)
        write_json(self.recheck, self.rp)

    def run_merge(self, **kwargs):
        return merge(self.original, self.recheck, self.original_manifest, self.recheck_manifest,
                     self.auto, self.out, **kwargs)

    def assert_rejected(self, pattern, **kwargs):
        with self.assertRaisesRegex(ValueError, pattern):
            self.run_merge(**kwargs)
        self.assertFalse(self.out.exists())

    def test_complete_merge_preserves_sources_rows_and_nonhuman_schema(self):
        before = {p: p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        result = self.run_merge()
        self.assertEqual(result['sample_size'], 5)
        self.assertEqual(result['rechecked_count'], 4)
        for path, content in before.items():
            self.assertEqual(path.read_bytes(), content)
        provenance = read_json(self.out / 'source_manifest.json')
        for info in provenance['sources'].values():
            self.assertEqual((self.out / info['preserved_copy']).read_bytes(), Path(info['path']).read_bytes())
        for name, expected in provenance['output_hashes'].items():
            self.assertEqual(digest(self.out / name), expected)
        for name in AUTO_FILES:
            self.assertEqual((self.out / 'sources/automatic' / name).read_bytes(), (self.auto / name).read_bytes())
        joined = read_json(self.out / 'joined_records.json')
        self.assertEqual(joined['schema_version'], SCHEMA)
        self.assertNotEqual(joined['schema_version'], EXPORT_SCHEMA)
        self.assertNotEqual(joined['label_source'], 'human')
        self.assertNotIn('labels', joined)
        self.assertEqual([r['case_id'] for r in joined['records']], [f'c{i}' for i in range(5)])
        retained = joined['records'][4]
        self.assertEqual(retained['human'], self.op['labels'][4])
        self.assertEqual(retained['human_source'], 'original')
        self.assertIsNone(retained['recheck_human'])
        self.assertTrue(all('flag_codes' not in r for r in joined['records']))

    def test_counts_weights_uncertainty_and_timestamps_are_distinguished(self):
        self.run_merge()
        s = read_json(self.out / 'summary.json')
        self.assertEqual(s['label_changed_case_count'], 3)
        self.assertEqual(s['annotation_changed_case_count'], 3)
        self.assertEqual(s['timestamp_only_case_count'], 1)
        self.assertEqual(s['changed_field_counts'], {'label': 2, 'cover': 2, 'visibility': 2, 'note': 1})
        self.assertEqual(s['export_metadata']['original']['prior_model_exposure'], 'no')
        self.assertEqual(s['export_metadata']['recheck']['prior_model_exposure'], 'no')
        self.assertIn('unknown', s['reviewer_relationship'])
        uncertainty = s['remaining_human_uncertainty']
        self.assertEqual(uncertainty['case_count'], 2)
        self.assertEqual(uncertainty['field_counts']['label'], 2)
        self.assertEqual(uncertainty['design_weighted_field_counts']['label'], 3)
        self.assertEqual([r['case_id'] for r in uncertainty['cases']], ['c1', 'c4'])
        raw = s['merged_counts']['raw_unweighted_tables']['monitor']
        weighted = s['merged_counts']['design_weighted_counts']['tables']['monitor']
        self.assertEqual(raw['no_hand']['OBJECT'], 2)
        self.assertEqual(weighted['no_hand']['OBJECT'], 3)
        self.assertEqual(raw['uncertain'], {'HUMAN': 1, 'OBJECT': 1, 'ERROR': 0})
        self.assertEqual(s['by_human_hand_condition']['glove/partial']['unique_run_count'], 1)
        self.assertEqual(s['by_run']['r2']['reviewed_frame_count'], 2)
        self.assertEqual(sum(t['count'] for t in s['original_to_recheck_transitions']['label']), 4)

    def test_timestamp_and_annotator_only_changes_are_not_label_changes(self):
        self.rp['labels'] = deepcopy(self.op['labels'][:4])
        for row in self.rp['labels']:
            row['reviewed_at'] = '2026-09-25T03:00:00Z'
        self.sync()
        self.run_merge()
        s = read_json(self.out / 'summary.json')
        self.assertEqual(s['label_changed_case_count'], 0)
        self.assertEqual(s['annotation_changed_case_count'], 0)
        self.assertEqual(s['timestamp_only_case_count'], 4)

    def test_partial_requires_opt_in_and_retains_unreviewed_original(self):
        self.rp['labels'] = self.rp['labels'][:1]
        self.sync()
        self.assert_rejected('Incomplete')
        result = self.run_merge(allow_partial_recheck=True)
        self.assertEqual(result['status'], 'partial_targeted_recheck_merged')
        rows = read_json(self.out / 'joined_records.json')['records']
        self.assertEqual(rows[1]['human'], self.op['labels'][1])
        self.assertEqual(rows[1]['human_source'], 'original')

    def test_uncertain_conditions_and_notes_are_not_coerced(self):
        self.rp['labels'][2].update(cover='uncertain', visibility='uncertain')
        self.rp['labels'][3]['note'] = 'Only a note changed'
        self.sync()
        self.run_merge()
        s = read_json(self.out / 'summary.json')
        self.assertEqual(s['remaining_human_uncertainty']['field_counts'],
                         {'label': 2, 'cover': 1, 'visibility': 1})
        self.assertEqual(s['by_human_hand_condition']['uncertain/uncertain']['reviewed_frame_count'], 1)
        ledger = read_json(self.out / 'changes.json')['rows']
        note_only = next(row for row in ledger if row['case_id'] == 'c3')
        self.assertFalse(note_only['label_changed'])
        self.assertTrue(note_only['annotation_changed'])

    def test_empty_partial_retains_every_original_row(self):
        self.rp['labels'] = []
        self.sync()
        self.assert_rejected('Incomplete')
        self.run_merge(allow_partial_recheck=True)
        rows = read_json(self.out / 'joined_records.json')['records']
        self.assertEqual([row['human'] for row in rows], self.op['labels'])

    def test_both_exports_are_validated_for_duplicate_labels(self):
        self.op['labels'].append(deepcopy(self.op['labels'][0]))
        self.sync()
        self.assert_rejected('Duplicate annotation')
        self.op['labels'].pop()
        self.rp['labels'].append(deepcopy(self.rp['labels'][0]))
        self.sync()
        self.assert_rejected('Duplicate annotation')

    def test_duplicate_recheck_manifest_case_is_rejected(self):
        self.rm['frames'].append(deepcopy(self.rm['frames'][0]))
        self.sync()
        self.assert_rejected('duplicate review manifest')

    def test_recheck_must_be_original_subset(self):
        self.rm['frames'][0]['case_id'] = 'intruder'
        self.rp['labels'][0]['id'] = 'intruder'
        self.sync()
        self.assert_rejected('not a subset')

    def test_recheck_must_preserve_original_metadata(self):
        for key, value in [('original_id', 'o6'), ('run', 'changed'), ('inclusion_weight', 500),
                           ('stratum', 'both_negative')]:
            before = self.rm['frames'][0][key]
            self.rm['frames'][0][key] = value
            self.sync()
            with self.subTest(key=key):
                self.assert_rejected('original frame metadata mismatch')
            self.rm['frames'][0][key] = before

    def test_original_hash_and_manifest_origin_bindings_are_required(self):
        for key in ('original_human_export_sha256', 'original_sample_manifest_sha256'):
            self.sync()
            self.rm['provenance'][key] = 'wrong'
            write_json(self.recheck_manifest, self.rm)
            self.rp['review_manifest_sha256'] = digest(self.recheck_manifest)
            write_json(self.recheck, self.rp)
            with self.subTest(key=key):
                self.assert_rejected('origin binding')

    def test_source_image_hash_is_checked(self):
        (self.root / 'semantic_audit/frames/0.jpg').write_bytes(b'tampered image')
        self.assert_rejected('image hash')

    def test_different_valid_image_in_recheck_is_rejected(self):
        for field in ('image', 'image_sha256'):
            self.rm['frames'][0][field] = self.om['frames'][1][field]
        self.sync()
        self.assert_rejected('original frame metadata mismatch')

    def test_all_frozen_automatic_files_are_checked(self):
        (self.auto / 'summary.json').write_text('{}')
        self.assert_rejected('Frozen automatic provenance hash mismatch')

    def test_recheck_automatic_provenance_must_match(self):
        self.rm['provenance']['automatic_audit_hashes']['summary.json'] = 'wrong'
        self.sync()
        self.assert_rejected('automatic provenance mismatch')

    def test_original_weights_are_checked(self):
        self.om['frames'][4]['inclusion_weight'] = 100
        self.sync()
        self.assert_rejected('sampling weight mismatch')

    def test_existing_output_is_never_overwritten(self):
        self.out.mkdir()
        sentinel = self.out / 'sentinel.txt'
        sentinel.write_text('untouched')
        with self.assertRaisesRegex(ValueError, 'Refusing to overwrite'):
            self.run_merge()
        self.assertEqual(sentinel.read_text(), 'untouched')


if __name__ == '__main__':
    unittest.main()
