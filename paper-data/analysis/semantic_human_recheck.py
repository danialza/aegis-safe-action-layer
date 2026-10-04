"""Freeze a targeted second human review without changing any original labels.

Model disagreements are review flags, never proof that a human is wrong. The
targeted queue is not a new independent test set and has no sampling estimator.
"""
from __future__ import annotations

import argparse
from collections import Counter
from copy import deepcopy
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil

from semantic_auto_report import digest, load_run, read_json
from semantic_human_review import SCHEMA, validate_export, write_json

ROOT = Path(__file__).resolve().parent.parent
SOURCE_HUMAN = Path('/Users/danial/Downloads/human_review_426_2026-09-24T21-55-53-540Z.json')
ORIGINAL_MANIFEST = ROOT / 'semantic_human_review/review_426_v1/manifest.json'
AUTO_SOURCE = ROOT / 'semantic_auto_audit/run_20260924_203640'
DEST = ROOT / 'semantic_human_review/recheck_115_v1'
TEMPLATE = ROOT / 'analysis/semantic_human_template.html'
FLAG_NAMES = (
    'human_presence_uncertain', 'human_condition_uncertain',
    'human_vs_reference_presence', 'human_vs_monitor_presence',
    'cover_disagreement', 'visibility_disagreement',
)
CAUTION = (
    'Provisional first-pass human labels. Model disagreement is not a human error. '
    'Targeted re-review is adjudication, not another independent test sample. '
    'Uncertain labels are retained. Prior model exposure needs user clarification; '
    'the original declaration is preserved and no blinding claim is made.'
)


def flags_for(human, automatic):
    """Presence comparisons require definite labels; condition comparisons also require hands."""
    flags = []
    reference, monitor = automatic['reference'], automatic['monitor']
    if human['label'] == 'uncertain':
        flags.append('human_presence_uncertain')
    if human['label'] == 'hand' and ('uncertain' in (human['cover'], human['visibility'])):
        flags.append('human_condition_uncertain')
    if human['label'] in {'hand', 'no_hand'}:
        if reference['presence'] in {'hand', 'no_hand'} and human['label'] != reference['presence']:
            flags.append('human_vs_reference_presence')
        monitor_presence = {'HUMAN': 'hand', 'OBJECT': 'no_hand'}.get(monitor['prediction'])
        if monitor_presence is not None and human['label'] != monitor_presence:
            flags.append('human_vs_monitor_presence')
    if human['label'] == reference['presence'] == 'hand':
        if human['cover'] in {'bare', 'glove', 'mixed'} and reference['cover'] in {'bare', 'glove'}:
            if human['cover'] != reference['cover']:
                flags.append('cover_disagreement')
        if human['visibility'] in {'full', 'partial'} and reference['visibility'] in {'full', 'partial'}:
            if human['visibility'] != reference['visibility']:
                flags.append('visibility_disagreement')
    return flags


def join_human(manifest, payload, automatic_rows):
    """Join validated original IDs without modifying frame records or human responses."""
    labels = {r['id']: r for r in payload['labels']}
    autos = {r['id']: r for r in automatic_rows}
    if len(labels) != len(payload['labels']) or len(autos) != len(automatic_rows):
        raise ValueError('Duplicate human or automatic IDs')
    frames = manifest['frames']
    if len({r['case_id'] for r in frames}) != len(frames) or set(labels) != {r['case_id'] for r in frames}:
        raise ValueError('Complete original human sample required')
    result = []
    for i, frame in enumerate(frames, 1):
        auto = autos[frame['original_id']]
        if auto['reference'].get('image_sha256') != frame['image_sha256'] or auto['monitor'].get('image_sha256') != frame['image_sha256']:
            raise ValueError('Original sample/automatic image identity mismatch')
        human = labels[frame['case_id']]
        flags = flags_for(human, auto)
        priority = 0 if 'human_presence_uncertain' in flags else 1 if 'human_condition_uncertain' in flags else 2
        result.append({'frame': deepcopy(frame), 'human': deepcopy(human),
                       'automatic': auto, 'flag_codes': flags,
                       'priority': priority, 'original_display_index': i})
    return result


def queue_frames(joined):
    flagged = sorted((r for r in joined if r['flag_codes']),
                     key=lambda r: (r['priority'], r['original_display_index']))
    return [dict(deepcopy(r['frame']), flag_codes=list(r['flag_codes']),
                 priority=r['priority'], original_display_index=r['original_display_index']) for r in flagged]


def table(rows, role, weighted=False):
    predictions = ('HUMAN', 'OBJECT', 'ERROR') if role == 'monitor' else ('hand', 'no_hand', 'uncertain', 'error')
    result = {human: {pred: 0 for pred in predictions} for human in ('hand', 'no_hand', 'uncertain')}
    for row in rows:
        prediction = row['automatic'][role]['prediction' if role == 'monitor' else 'presence']
        result[row['human']['label']][prediction] += row['frame']['inclusion_weight'] if weighted else 1
    return result


def summarize(joined, payload):
    flags = Counter(flag for row in joined for flag in row['flag_codes'])
    queue = [r for r in joined if r['flag_codes']]
    presence = Counter(r['human']['label'] for r in joined)
    weighted_presence = Counter()
    for row in joined:
        weighted_presence[row['human']['label']] += row['frame']['inclusion_weight']
    return {
        'status': 'provisional_first_pass_pending_targeted_human_recheck',
        'caution': CAUTION,
        'original_human_metadata': {k: v for k, v in payload.items() if k != 'labels'},
        'exposure_status': 'Original declaration retained verbatim; pending user clarification. Do not claim blinded assessment.',
        'original_human_counts': dict(presence),
        'original_hand_cover_counts': dict(Counter(r['human']['cover'] for r in joined if r['human']['label'] == 'hand')),
        'original_hand_visibility_counts': dict(Counter(r['human']['visibility'] for r in joined if r['human']['label'] == 'hand')),
        'sample_size': len(joined),
        'flag_counts_nonexclusive': {flag: flags[flag] for flag in FLAG_NAMES},
        'recheck_unique_count': len(queue),
        'priority_counts': {str(p): sum(r['priority'] == p for r in queue) for p in range(3)},
        'flag_overlap_pattern_counts': dict(Counter('|'.join(r['flag_codes']) for r in queue)),
        'raw_unweighted_tables': {role: table(joined, role) for role in ('monitor', 'reference')},
        'weighted_finite_population_counts': {
            'interpretation': 'Design-weighted point counts over the original 2158-frame population, NOT counts directly reviewed. No confidence interval or independence claim.',
            'human_presence': dict(weighted_presence),
            'tables': {role: table(joined, role, weighted=True) for role in ('monitor', 'reference')},
        },
        'metric_limitations': [
            'Raw sample is enriched by model strata; raw agreement is not population accuracy.',
            'Zero observed false negatives does not establish perfect recall, especially in unsampled jointly negative frames.',
            'Uncertain presence and conditions are retained, not imputed from either model.',
            'Frames are correlated within runs; no per-frame independent-binomial inference is provided.',
            'Single-session retrospective current-checkpoint video replay is not independent-session or live-input validation.',
            'Targeted queue must be merged by case ID back into the original sample; do not analyze it as a new representative sample.',
        ],
    }


def render_ui(template_text, frames, manifest_sha):
    replacements = {
        '<title>بررسی انسانی تصاویر دست</title>': '<title>بازبینی انسانی موارد نیازمند بررسی دوباره</title>',
        '<h1>آیا دست انسان در تصویر دیده می‌شود؟</h1>': '<h1>بازبینی انسانی: آیا دست در تصویر دیده می‌شود؟</h1>',
        "'aegis-human-426-'": "'aegis-human-recheck-'",
        "'human_review_426_'": "'human_recheck_115_'",
    }
    for original, replacement in replacements.items():
        if template_text.count(original) != 1:
            raise ValueError('Unexpected annotation template; scoped replacement failed: ' + original)
        template_text = template_text.replace(original, replacement)
    n = len(frames)
    first = sum(row['priority'] < 2 for row in frames)
    notice = (
        f'<p class="notice">این صف {n} تصویر منتخب برای بازبینی دارد؛ {first} تصویر نخست '
        'در پاسخ قبلی ابهام داشتند. اختلاف مدل با شما به معنی اشتباه شما نیست. '
        'پاسخ مدل‌ها و برچسب قبلی نمایش داده نمی‌شود. فقط تصویر را دوباره بررسی کنید؛ '
        'اگر ابهام رفع نمی‌شود «نامشخص» را نگه دارید. پاسخ‌های جدید جدا ذخیره می‌شوند '
        'و برچسب‌های اصلی تغییر نمی‌کنند. لازم نیست همهٔ موارد را اصلاح کنید؛ '
        f'می‌توانید فقط {first} مورد نخست را بررسی و JSON ناقص را دانلود کنید. '
        'موارد بررسی‌نشده در ادغام بعدی همان نظر انسانی اصلی را نگه می‌دارند. '
        'این مرحله بازبینی هدفمند است، نه آزمون مستقل تازه.</p>'
    )
    if template_text.count('</header>') != 1:
        raise ValueError('Unexpected template header')
    template_text = template_text.replace('</header>', notice + '\n</header>')
    # Only IDs and image paths enter the annotation UI: flags, previous labels,
    # predictions, ordering metadata and weights stay in analyst files.
    ui_frames = [{'id': row['case_id'], 'image': row['image']} for row in frames]
    for token in ('__FRAME_DATA__', '__MANIFEST_SHA__'):
        if template_text.count(token) != 1:
            raise ValueError('Unexpected replacement-token count: ' + token)
    template_text = template_text.replace('__FRAME_DATA__', json.dumps(ui_frames, ensure_ascii=False))
    template_text = template_text.replace('__MANIFEST_SHA__', manifest_sha)
    template_text = template_text.replace('max="426"', f'max="{n}"')
    return template_text, ui_frames


def report_fa(summary):
    c = summary['original_human_counts']
    f = summary['flag_counts_nonexclusive']
    m = summary['raw_unweighted_tables']['monitor']
    return f"""# نتیجهٔ موقت بررسی انسانی و صف بازبینی

هر {summary['sample_size']} پاسخ انسانی ثبت شده است: {c.get('hand', 0)} تصویر دست‌دار، {c.get('no_hand', 0)} بدون دست و {c.get('uncertain', 0)} نامشخص. در {summary['original_hand_cover_counts'].get('glove', 0)} تصویر دستکش ثبت شده است. این پاسخ‌ها دست‌نخورده و با هش نگه‌داری شده‌اند؛ هیچ مدل یا اسکریپتی نظر انسانی را اصلاح نکرده است.

## موارد منتخب برای بازبینی

صف {summary['recheck_unique_count']} تصویر یکتا دارد. شمارش دلیل‌ها هم‌پوشانی دارد و نباید جمع شود:

- حضور دست نامشخص: {f['human_presence_uncertain']}.
- پوشش یا میزان دیده‌شدن دست نامشخص: {f['human_condition_uncertain']}.
- اختلاف حضور دست با مدل مرجع خودکار: {f['human_vs_reference_presence']}.
- اختلاف حضور دست با FastVLM: {f['human_vs_monitor_presence']}.
- اختلاف قطعی در نوع پوشش دست: {f['cover_disagreement']}.
- اختلاف قطعی در میزان دیده‌شدن دست: {f['visibility_disagreement']}.

ابتدا موارد نامشخص نمایش داده می‌شوند و سپس بقیه به ترتیب نمایش اصلی. اختلاف با مدل اثبات اشتباه انسان نیست؛ اگر نظر قبلی درست است همان را دوباره ثبت کنید و اگر تصویر قابل قضاوت نیست «نامشخص» را نگه دارید. صفحه هیچ پاسخ پیشنهادی، رأی مدل یا برچسب قبلی ندارد.

## شمارش موقت، نه نتیجهٔ نهایی مقاله

در نمونهٔ برچسب‌خورده و فقط میان پاسخ‌های قطعی انسانی، FastVLM دارای {m['hand']['HUMAN']} مثبت درست، {m['no_hand']['HUMAN']} مثبت کاذب، {m['no_hand']['OBJECT']} منفی درست و {m['hand']['OBJECT']} منفی کاذب نسبت به نظر فعلی انسان است. مورد نامشخص حذف یا منفی فرض نشده است. صفر منفی کاذب مشاهده‌شده، اثبات حساسیت کامل نیست: تمام تصاویر توافق منفی بازبینی نشده‌اند و فریم‌ها هم‌بسته‌اند.

این نمونه عمداً از اختلاف‌ها غنی شده؛ درصد خام را به‌عنوان دقت در کل ۲۱۵۸ تصویر گزارش نکنید. `summary.json` شمارش خام و شمارش وزن‌دار طراحی نمونه‌گیری را جدا نگه می‌دارد. وزن‌دار بودن جای عدم‌قطعیت، بررسی هم‌بستگی و مرجع انسانی معتبر را نمی‌گیرد. صف جدید نمونهٔ مستقل یا نماینده نیست؛ پس از دریافت پاسخ، باید با شناسه به نمونهٔ ۴۲۶تایی اصلی وصل شود و سابقهٔ هر تغییر حفظ شود.

## وضعیت سابقهٔ مشاهدهٔ مدل

فایل اصلی مقدار `{summary['original_human_metadata']['prior_model_exposure']}` را برای مشاهدهٔ قبلی مدل ثبت کرده است. همان مقدار بدون تغییر حفظ شده است؛ با توجه به گزارش‌های قبلی، این موضوع نیاز به توضیح خود بررسی‌کننده دارد. فعلاً این ارزیابی را کور یا مستقل از مواجههٔ قبلی با پاسخ مدل اعلام نمی‌کنیم. در فرم جدید سابقهٔ مشاهده را مطابق واقعیت ثبت کنید.

## استفاده

`label_review.html` را باز کنید و پاسخ‌ها را از ابتدا، فقط بر اساس تصویر ثبت کنید. ابتدا ۱۴ ابهام را بررسی کنید؛ لازم نیست ۱۱۵ پاسخ را تغییر دهید. می‌توانید پس از همین ۱۴ مورد JSON ناقص را دانلود و ارسال کنید. اعتبارسنج موجود فایل ناقص را می‌پذیرد؛ در ادغام بعدی، موارد بازبینی‌نشده باید همان برچسب انسانی اصلی را نگه دارند. ساعدِ تنها بدون دست یا انگشت، وجود دست محسوب نمی‌شود؛ لبهٔ تصویر فقط وقتی «دست بخشی پنهان» است که واقعاً بخشی از دست/انگشت تشخیص داده شود. در ابهام «نامشخص» را نگه دارید.

ذخیرهٔ مرورگر و نام فایل خروجی جدید جدا هستند. فایل اصلی ۴۲۶ پاسخ و تمام داده‌های خام حفظ شده‌اند؛ این مرحله هیچ مقاله، لاگ ربات، ویدیو یا برچسب قبلی را تغییر نمی‌دهد. پس از بازبینی JSON جدید را دانلود کنید.
"""


def prepare(source_human=SOURCE_HUMAN, original_manifest=ORIGINAL_MANIFEST,
            auto_source=AUTO_SOURCE, dest=DEST, template=TEMPLATE, expected_count=115):
    dest = Path(dest).resolve()
    if dest.exists():
        raise ValueError('Refusing to overwrite existing recheck directory: ' + str(dest))
    source_human = Path(source_human).resolve(strict=True)
    original_manifest = Path(original_manifest).resolve(strict=True)
    auto_source = Path(auto_source).resolve(strict=True)
    template = Path(template).resolve(strict=True)
    source_hash = digest(source_human)
    manifest_hash = digest(original_manifest)
    validation = validate_export(source_human, original_manifest, require_complete=True)
    original = read_json(original_manifest)
    payload = read_json(source_human)
    _, auto_rows = load_run(auto_source)
    auto_hashes = original['provenance']['automatic_audit_hashes']
    for name, expected in auto_hashes.items():
        if Path(name).name != name or digest(auto_source / name) != expected:
            raise ValueError('Original sample automatic provenance hash mismatch: ' + name)
    joined = join_human(original, payload, auto_rows)
    frames = queue_frames(joined)
    if expected_count is not None and len(frames) != expected_count:
        raise ValueError(f'Queue count differs from expected frozen design: {len(frames)} != {expected_count}')
    if not frames:
        raise ValueError('No recheck flags; no output created')
    summary = summarize(joined, payload)
    recheck = {
        'schema_version': SCHEMA,
        'created_utc': datetime.now(timezone.utc).isoformat(),
        'purpose': 'Targeted human adjudication/recheck; NOT an independent test sample or basis for fresh accuracy estimation.',
        'provenance': {
            'original_sample_manifest': str(original_manifest),
            'original_sample_manifest_sha256': manifest_hash,
            'original_human_export': str(source_human),
            'original_human_export_sha256': source_hash,
            'original_human_export_preserved_copy': 'original_human_export.json',
            'automatic_audit_directory': str(auto_source),
            'automatic_audit_hashes': auto_hashes,
            'queue_code_sha256': digest(__file__),
            'template_sha256_at_freeze': digest(template),
        },
        'selection': {
            'count': len(frames), 'original_sample_size': len(joined),
            'flag_definitions': list(FLAG_NAMES), 'flag_counts_nonexclusive': summary['flag_counts_nonexclusive'],
            'ordering': 'Presence uncertainty first, condition uncertainty second, other flags third; original display order within each priority.',
            'sampling_interpretation': 'Targeted and conditioned on human/model outcomes. Original inclusion weights are provenance only; merge revised labels back by case ID, never estimate from this queue alone.',
        },
        'blinding': {
            'ui_fields': ['id', 'image'],
            'hidden_from_annotation_ui': ['prior human label', 'model predictions', 'flag codes', 'stratum', 'original display index', 'run', 'sampling weights'],
            'limitation': 'Prior exposure cannot be undone. No assertion of blinded or independent adjudication.',
        },
        'scope': CAUTION,
        'frames': frames,
    }
    # Validate scoped rendering before creating any output directory.
    render_ui(template.read_text(), frames, 'preflight')
    if digest(source_human) != source_hash or digest(original_manifest) != manifest_hash:
        raise ValueError('Source changed during validation; no output created')
    dest.mkdir(parents=True)
    shutil.copyfile(source_human, dest / 'original_human_export.json')
    if digest(dest / 'original_human_export.json') != source_hash:
        raise ValueError('Exact human export copy verification failed')
    write_json(dest / 'manifest.json', recheck)
    html, ui_frames = render_ui(template.read_text(), frames, digest(dest / 'manifest.json'))
    write_json(dest / 'ui_frames.json', ui_frames)
    (dest / 'label_review.html').write_text(html)
    summary['provenance'] = recheck['provenance']
    summary['original_export_validation'] = validation
    summary['recheck_manifest_sha256'] = digest(dest / 'manifest.json')
    write_json(dest / 'summary.json', summary)
    (dest / 'report_FA.md').write_text(report_fa(summary))
    if digest(source_human) != source_hash or digest(original_manifest) != manifest_hash:
        raise ValueError('Source changed during generation; investigate before using output')
    return {'destination': str(dest), 'count': len(frames),
            'priority_counts': summary['priority_counts'], 'flag_counts': summary['flag_counts_nonexclusive'],
            'original_human_export_sha256': source_hash,
            'original_sample_manifest_sha256': manifest_hash,
            'recheck_manifest_sha256': digest(dest / 'manifest.json'),
            'status': 'awaiting genuine human recheck; no human answer prefilled or changed'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-human', type=Path, default=SOURCE_HUMAN)
    parser.add_argument('--original-manifest', type=Path, default=ORIGINAL_MANIFEST)
    parser.add_argument('--auto-source', type=Path, default=AUTO_SOURCE)
    parser.add_argument('--dest', type=Path, default=DEST)
    parser.add_argument('--template', type=Path, default=TEMPLATE)
    args = parser.parse_args()
    try:
        result = prepare(args.source_human, args.original_manifest, args.auto_source, args.dest, args.template)
    except (ValueError, OSError, KeyError, TypeError) as exc:
        parser.exit(2, 'ERROR: ' + str(exc) + '\n')
    print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))


if __name__ == '__main__':
    main()
