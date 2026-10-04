"""Merge two validated human exports into a NEW, analysis-only artifact.

No labels are inferred, no source is edited, and no model disagreement is treated
as an unresolved human error. Complete recheck exports are required by default.
"""
from __future__ import annotations

import argparse
from collections import Counter
from copy import deepcopy
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import shutil

from semantic_auto_report import digest, load_run, read_json
from semantic_human_recheck import join_human, table
from semantic_human_review import STRATA, stratum_of, validate_export, write_json

SCHEMA = 'aegis-human-merged-analysis-v1'
ANNOTATION_FIELDS = ('label', 'cover', 'visibility', 'note')
LABEL_FIELDS = ('label', 'cover', 'visibility')
AUTO_FILES = {
    'spec.json', 'frame_mapping.json', 'reference.jsonl', 'monitor.jsonl',
    'reference.sealed.json', 'monitor.sealed.json', 'summary.json',
    'reference_checkpoint.json', 'monitor_checkpoint.json',
}
LIMITATIONS = [
    'Analysis-only merge of two human-declared exports, not a new single human export.',
    'The original sample is model-stratified and enriched; raw fractions are not population accuracy.',
    'Design-weighted counts are finite-population point estimates, not directly reviewed counts; no confidence intervals are calculated.',
    'The targeted recheck is not an independent or representative sample and has no separate population estimator.',
    'Reviewer names do not establish whether this was the same person or a second independent reviewer; that relationship is unknown.',
    'Both prior_model_exposure declarations are preserved verbatim; no blinded or independent assessment is claimed.',
    'Uncertain human labels remain uncertain, never replaced by model answers. Persistent model disagreement is not unresolved human error.',
    'Correlated, same-session video frames do not establish new-session generalization, exact historical live input, timing, or physical safety.',
    'Zero observed misses does not prove zero misses among unsampled frames.',
]


def metadata(payload):
    return deepcopy({k: v for k, v in payload.items() if k != 'labels'})


def validate_bindings(original_manifest, recheck_manifest, original_hash, manifest_hash):
    provenance = recheck_manifest['provenance']
    if provenance.get('original_human_export_sha256') != original_hash:
        raise ValueError('Recheck origin binding: original human export hash mismatch')
    if provenance.get('original_sample_manifest_sha256') != manifest_hash:
        raise ValueError('Recheck origin binding: original sample manifest hash mismatch')
    originals = {f['case_id']: f for f in original_manifest['frames']}
    original_ids = [f['original_id'] for f in original_manifest['frames']]
    if len(set(original_ids)) != len(original_ids):
        raise ValueError('Duplicate original frame ID in original manifest')
    frames = recheck_manifest['frames']
    for frame in frames:
        key = frame['case_id']
        if key not in originals:
            raise ValueError('Recheck case is not a subset of the original sample: ' + key)
        # All original fields, including image, run, stratum and weight, are frozen.
        for field, value in originals[key].items():
            if field not in frame or frame[field] != value:
                raise ValueError('Recheck original frame metadata mismatch: ' + key + '/' + field)
    selection = recheck_manifest['selection']
    if selection.get('count') != len(frames) or selection.get('original_sample_size') != len(originals):
        raise ValueError('Recheck frozen selection count mismatch')


def validate_design(manifest, automatic):
    autos = {r['id']: r for r in automatic}
    populations = {s: 0 for s in STRATA}
    counts = {s: 0 for s in STRATA}
    for row in automatic:
        populations[stratum_of(row)] += 1
    for frame in manifest['frames']:
        auto = autos.get(frame['original_id'])
        if auto is None or frame['stratum'] != stratum_of(auto):
            raise ValueError('Original sample automatic ID/stratum mismatch')
        if any(frame[k] != auto[k] for k in ('run', 'campaign', 'container_time_s', 'image')):
            raise ValueError('Original sample automatic frame metadata mismatch')
        counts[frame['stratum']] += 1
    sampling = manifest['sampling']
    expected = {'population_size': len(automatic), 'sample_size': len(manifest['frames']),
                'population_counts': populations, 'sample_counts': counts}
    if any(sampling.get(k) != v for k, v in expected.items()):
        raise ValueError('Original frozen sampling counts mismatch')
    for frame in manifest['frames']:
        n, N = counts[frame['stratum']], populations[frame['stratum']]
        for field, expected_value in (('inclusion_weight', N / n), ('inclusion_probability', n / N)):
            value = frame[field]
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not math.isclose(value, expected_value, rel_tol=1e-12):
                raise ValueError('Original frozen sampling weight mismatch: ' + frame['case_id'])


def merge_records(original_manifest, original, recheck, automatic, source_hashes):
    """Called after validation; preserve original ordering and untouched rows."""
    revisions = {r['id']: r for r in recheck['labels']}
    records, ledger = [], []
    for joined in join_human(original_manifest, original, automatic):
        frame, old = joined['frame'], joined['human']
        key = frame['case_id']
        revised = revisions.get(key)
        source = 'recheck' if revised is not None else 'original'
        effective = deepcopy(revised if revised is not None else old)
        records.append({
            'case_id': key, 'frame': frame, 'human': effective,
            'human_source': source, 'human_source_sha256': source_hashes[source],
            'original_human': deepcopy(old), 'original_source_sha256': source_hashes['original'],
            'recheck_human': deepcopy(revised),
            'recheck_source_sha256': source_hashes['recheck'] if revised is not None else None,
            'automatic': deepcopy(joined['automatic']),
            'original_display_index': joined['original_display_index'],
        })
        if revised is not None:
            changes = {f: {'from': deepcopy(old[f]), 'to': deepcopy(revised[f])}
                       for f in ANNOTATION_FIELDS if old[f] != revised[f]}
            ledger.append({'case_id': key, 'changed_fields': changes,
                           'label_changed': any(f in changes for f in LABEL_FIELDS),
                           'annotation_changed': bool(changes),
                           'reviewed_at_changed': old['reviewed_at'] != revised['reviewed_at'],
                           'original_reviewed_at': old['reviewed_at'],
                           'recheck_reviewed_at': revised['reviewed_at']})
    return records, ledger


def counts(rows):
    weighted = Counter()
    for row in rows:
        weighted[row['human']['label']] += row['frame']['inclusion_weight']
    hand_rows = [r for r in rows if r['human']['label'] == 'hand']
    runs = sorted({r['frame']['run'] for r in rows})
    return {
        'reviewed_frame_count': len(rows), 'unique_run_count': len(runs), 'runs': runs,
        'human_presence': dict(Counter(r['human']['label'] for r in rows)),
        'human_hand_cover': dict(Counter(r['human']['cover'] for r in hand_rows)),
        'human_hand_visibility': dict(Counter(r['human']['visibility'] for r in hand_rows)),
        'raw_unweighted_tables': {role: table(rows, role) for role in ('monitor', 'reference')},
        'design_weighted_counts': {
            'human_presence': dict(weighted),
            'tables': {role: table(rows, role, weighted=True) for role in ('monitor', 'reference')},
        },
    }


def breakdown(rows, key):
    groups = {}
    for row in rows:
        groups.setdefault(key(row), []).append(row)
    return {group: counts(group_rows) for group, group_rows in sorted(groups.items())}


def transitions(records):
    """All original-to-recheck field transitions, including unchanged responses."""
    result = {}
    for field in ANNOTATION_FIELDS:
        pairs = Counter((r['original_human'][field], r['recheck_human'][field])
                        for r in records if r['recheck_human'] is not None)
        result[field] = [{'from': before, 'to': after, 'count': count}
                         for (before, after), count in sorted(pairs.items(), key=lambda x: repr(x[0]))]
    return result


def summarize(records, ledger, original, recheck, original_manifest, recheck_manifest, validations):
    remaining = []
    for row in records:
        h = row['human']
        fields = [f for f in LABEL_FIELDS if h[f] == 'uncertain']
        if fields:
            remaining.append({'case_id': row['case_id'], 'uncertain_fields': fields,
                              'human_source': row['human_source'],
                              'inclusion_weight': row['frame']['inclusion_weight']})
    hands = [r for r in records if r['human']['label'] == 'hand']
    first_pass = [dict(r, human=r['original_human']) for r in records]
    return {
        'schema_version': SCHEMA, 'label_source': 'derived_analysis_of_human_exports',
        'status': 'complete_targeted_recheck_merged' if validations['recheck']['complete'] else 'partial_targeted_recheck_merged',
        'limitations': LIMITATIONS, 'export_metadata': {'original': metadata(original), 'recheck': metadata(recheck)},
        'reviewer_relationship': 'unknown; annotator names alone do not establish independent reviewers',
        'validations': validations, 'original_sampling': deepcopy(original_manifest['sampling']),
        'original_sample_size': len(records), 'targeted_recheck_size': len(recheck_manifest['frames']),
        'rechecked_count': len(ledger), 'not_rechecked_retained_original_count': len(records) - len(ledger),
        'label_changed_case_count': sum(x['label_changed'] for x in ledger),
        'annotation_changed_case_count': sum(x['annotation_changed'] for x in ledger),
        'timestamp_only_case_count': sum(x['reviewed_at_changed'] and not x['annotation_changed'] for x in ledger),
        'changed_field_counts': {f: sum(f in x['changed_fields'] for x in ledger) for f in ANNOTATION_FIELDS},
        'original_to_recheck_transitions': transitions(records),
        'remaining_human_uncertainty': {
            'case_count': len(remaining), 'cases': remaining,
            'field_counts': {f: sum(f in r['uncertain_fields'] for r in remaining) for f in LABEL_FIELDS},
            'design_weighted_field_counts': {f: sum(r['inclusion_weight'] for r in remaining if f in r['uncertain_fields']) for f in LABEL_FIELDS},
            'interpretation': 'Human-declared uncertainty only; model disagreement is not a flag or unresolved human error.',
        },
        'original_counts': counts(first_pass), 'merged_counts': counts(records),
        'by_run': breakdown(records, lambda r: r['frame']['run']),
        'by_campaign': breakdown(records, lambda r: r['frame']['campaign']),
        'by_stratum': breakdown(records, lambda r: r['frame']['stratum']),
        'by_human_hand_cover': breakdown(hands, lambda r: r['human']['cover']),
        'by_human_hand_visibility': breakdown(hands, lambda r: r['human']['visibility']),
        'by_human_hand_condition': breakdown(hands, lambda r: r['human']['cover'] + '/' + r['human']['visibility']),
    }


def merge(original, recheck, original_manifest, recheck_manifest, auto_source, outdir,
          allow_partial_recheck=False):
    outdir = Path(outdir).resolve()
    if outdir.exists():
        raise ValueError('Refusing to overwrite existing analysis directory: ' + str(outdir))
    paths = {name: Path(path).resolve(strict=True) for name, path in {
        'original': original, 'recheck': recheck,
        'original_manifest': original_manifest, 'recheck_manifest': recheck_manifest,
    }.items()}
    auto_source = Path(auto_source).resolve(strict=True)
    hashes = {name: digest(path) for name, path in paths.items()}
    validations = {
        'original': validate_export(paths['original'], paths['original_manifest'], require_complete=True),
        'recheck': validate_export(paths['recheck'], paths['recheck_manifest'], require_complete=not allow_partial_recheck),
    }
    data = {name: read_json(path) for name, path in paths.items()}
    validate_bindings(data['original_manifest'], data['recheck_manifest'], hashes['original'], hashes['original_manifest'])
    auto_hashes = data['original_manifest']['provenance']['automatic_audit_hashes']
    if not isinstance(auto_hashes, dict) or not AUTO_FILES.issubset(auto_hashes):
        raise ValueError('Original automatic provenance is incomplete')
    if data['recheck_manifest']['provenance'].get('automatic_audit_hashes') != auto_hashes:
        raise ValueError('Recheck/original automatic provenance mismatch')
    for name, expected in auto_hashes.items():
        if Path(name).name != name or name in {'.', '..'} or digest(auto_source / name) != expected:
            raise ValueError('Frozen automatic provenance hash mismatch: ' + name)
    _, automatic = load_run(auto_source)
    validate_design(data['original_manifest'], automatic)
    records, ledger = merge_records(data['original_manifest'], data['original'], data['recheck'], automatic, hashes)
    summary = summarize(records, ledger, data['original'], data['recheck'], data['original_manifest'], data['recheck_manifest'], validations)
    # Every check and calculation precedes output creation; no source is written.
    for name, path in paths.items():
        if digest(path) != hashes[name]:
            raise ValueError('Source changed during validation: ' + name)
    for name, expected in auto_hashes.items():
        if digest(auto_source / name) != expected:
            raise ValueError('Automatic source changed during validation: ' + name)
    outdir.mkdir(parents=True)
    (outdir / 'sources/automatic').mkdir(parents=True)
    source_records = {}
    for name, path in paths.items():
        copy_path = outdir / 'sources' / (name + '.json')
        shutil.copyfile(path, copy_path)
        if digest(copy_path) != hashes[name]:
            raise ValueError('Source bytecopy hash mismatch: ' + name)
        source_records[name] = {'path': str(path), 'sha256': hashes[name], 'preserved_copy': str(copy_path.relative_to(outdir))}
    for name, expected in auto_hashes.items():
        copy_path = outdir / 'sources/automatic' / name
        shutil.copyfile(auto_source / name, copy_path)
        if digest(copy_path) != expected:
            raise ValueError('Automatic source bytecopy hash mismatch: ' + name)
    write_json(outdir / 'joined_records.json', {'schema_version': SCHEMA, 'label_source': 'derived_analysis_of_human_exports',
               'export_metadata': summary['export_metadata'], 'records': records})
    write_json(outdir / 'changes.json', {'schema_version': SCHEMA, 'definition': 'One ledger row per rechecked case. Label changes exclude notes, timestamps and export-level identity metadata.',
               'rows': ledger, 'field_transitions': summary['original_to_recheck_transitions']})
    write_json(outdir / 'summary.json', summary)
    source_manifest = {'schema_version': SCHEMA, 'created_utc': datetime.now(timezone.utc).isoformat(),
        'sources': source_records, 'automatic_audit_directory': str(auto_source),
        'automatic_audit_hashes': auto_hashes, 'automatic_preserved_copies_directory': 'sources/automatic',
        'code_hashes': {name: digest(Path(__file__).with_name(name)) for name in
                        ('semantic_human_merge.py', 'semantic_human_review.py', 'semantic_human_recheck.py', 'semantic_auto_report.py')},
        'output_hashes': {name: digest(outdir / name) for name in ('joined_records.json', 'changes.json', 'summary.json')},
        'limitations': LIMITATIONS}
    write_json(outdir / 'source_manifest.json', source_manifest)
    return {'destination': str(outdir), 'status': summary['status'],
            'sample_size': len(records), 'rechecked_count': len(ledger),
            'label_changed_case_count': summary['label_changed_case_count'],
            'remaining_human_uncertainty_count': summary['remaining_human_uncertainty']['case_count']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('original', 'recheck', 'original-manifest', 'recheck-manifest', 'auto-source', 'outdir'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--allow-partial-recheck', action='store_true',
                        help='Explicitly retain original labels for unreviewed queued cases; default requires complete recheck.')
    args = parser.parse_args()
    try:
        result = merge(**vars(args))
    except (ValueError, OSError, KeyError, TypeError) as exc:
        parser.exit(2, 'ERROR: ' + str(exc) + '\n')
    print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))


if __name__ == '__main__':
    main()
