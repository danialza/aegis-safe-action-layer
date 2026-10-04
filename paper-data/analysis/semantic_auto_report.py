"""Report an automatic cross-model audit; no human ground truth is inferred.

Only writes derived reports inside the explicitly supplied run directory. The
human annotation manifest, labels, videos, and manuscript are never modified.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import html
import json
import math
from pathlib import Path, PurePosixPath
from urllib.parse import quote


PRESENCES = ("hand", "no_hand", "uncertain", "error")
PREDICTIONS = ("HUMAN", "OBJECT", "ERROR")
CODES = {"N", "U", "B0", "B1", "G0", "G1", "H0", "H1", "ERROR", "INVALID"}
LIMIT = (
    "Automatic cross-model agreement, not independently validated detection accuracy. "
    "Reference labels and condition strata are model estimates, not human ground truth. "
    "Correlated errors can make agreement high while both models are wrong. "
    "Current-checkpoint replay of lossy video-derived frames is not the historical live "
    "VLM input stream, live reaction latency, or evidence of physical/whole-arm safety. "
    "The available videos do not establish subject/session-disjoint generalization."
)
LIMIT_FA = (
    "این گزارش توافق دو مدل را می‌سنجد، نه دقت تأییدشده با مرجع انسانی مستقل. "
    "برچسب دست، دستکش و پوشیدگی همگی تخمین مدل مرجع هستند. دو مدل ممکن است هم‌زمان "
    "اشتباه کنند؛ توافق بالا اثبات صحت یا ایمنی نیست. این بازپخش آفلاینِ نسخهٔ فعلی مدل "
    "روی فریم‌های استخراج‌شده از ویدیو است، نه بازسازی دقیق ورودی زنده، زمان واکنش ربات "
    "یا آزمون تعمیم به افراد و جلسه‌های مستقل."
)


def digest(path):
    result = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            result.update(block)
    return result.hexdigest()


def read_json(path):
    def reject_constant(value):
        raise ValueError("Non-finite JSON value: " + value)
    return json.loads(Path(path).read_text(), parse_constant=reject_constant)


def read_jsonl(path):
    rows = []
    for line_number, line in enumerate(Path(path).read_text().splitlines(), 1):
        if not line.strip():
            continue
        try:
            row = json.loads(line, parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)))
        except (ValueError, TypeError) as exc:
            raise ValueError(f"Invalid JSON at {path}:{line_number}") from exc
        if not isinstance(row, dict):
            raise ValueError(f"Expected object at {path}:{line_number}")
        rows.append(row)
    return rows


def indexed(rows, name):
    result = {}
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get("id"), str) or not row["id"]:
            raise ValueError(name + ": missing/non-string frame ID")
        if row["id"] in result:
            raise ValueError(name + ": duplicate ID " + row["id"])
        result[row["id"]] = row
    return result


def check_duration(row, name):
    value = row.get("inference_s")
    if value is not None and (isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0):
        raise ValueError(name + ": invalid inference_s")


def load_run(run_dir):
    """Reject partial/mismatched data rather than producing a final-looking report."""
    run_dir = Path(run_dir).resolve(strict=True)
    spec = read_json(run_dir / "spec.json")
    if not isinstance(spec, dict):
        raise ValueError("spec.json must contain an object")
    mapping = read_json(run_dir / "frame_mapping.json")
    if not isinstance(mapping, list) or not mapping:
        raise ValueError("frame_mapping.json must be a nonempty list")
    maps = indexed(mapping, "mapping")
    if type(spec.get("total_frames")) is not int or spec["total_frames"] != len(maps):
        raise ValueError("Frozen specification frame count mismatch")
    if spec.get("mapping_sha256") != digest(run_dir / "frame_mapping.json"):
        raise ValueError("Frozen frame mapping hash mismatch")
    refs = indexed(read_jsonl(run_dir / "reference.jsonl"), "reference")
    monitors = indexed(read_jsonl(run_dir / "monitor.jsonl"), "monitor")
    for name, rows in (("reference", refs), ("monitor", monitors)):
        if set(rows) != set(maps):
            missing, unknown = set(maps) - set(rows), set(rows) - set(maps)
            raise ValueError(f"{name}: missing IDs={len(missing)}, unknown IDs={len(unknown)}; final report requires every mapped frame")
    spec_sha = digest(run_dir / "spec.json")
    for role in ("reference", "monitor"):
        seal = read_json(run_dir / f"{role}.sealed.json")
        if seal.get("spec_sha256") != spec_sha or seal.get("rows") != len(maps):
            raise ValueError(role + ": final seal specification/count mismatch")
        if seal.get("predictions_sha256") != digest(run_dir / f"{role}.jsonl"):
            raise ValueError(role + ": sealed prediction hash mismatch")
    audit_root = run_dir.parent.parent / "semantic_audit"
    joined = []
    for key, meta in maps.items():
        ref, monitor = refs[key], monitors[key]
        for role, row in (("reference", ref), ("monitor", monitor)):
            if row.get("spec_sha256") != spec_sha:
                raise ValueError(role + ": row belongs to another specification")
        if ref.get("label_source") != "model":
            raise ValueError("Automatic reference must explicitly use label_source=model")
        code, presence = ref.get("code"), ref.get("presence")
        if code not in CODES or presence not in PRESENCES:
            raise ValueError("Invalid reference code/presence for " + key)
        expected = "no_hand" if code == "N" else "uncertain" if code == "U" else "error" if code in {"ERROR", "INVALID"} else "hand"
        if presence != expected:
            raise ValueError("Reference code/presence mismatch for " + key)
        if ref.get("cover") not in {None, "bare", "glove", "unspecified"}:
            raise ValueError("Invalid model-estimated cover for " + key)
        if ref.get("visibility") not in {None, "full", "partial"}:
            raise ValueError("Invalid model-estimated visibility for " + key)
        if presence == "hand":
            if ref.get("cover") != {"B": "bare", "G": "glove", "H": "unspecified"}[code[0]] or ref.get("visibility") != ("full" if code[1] == "0" else "partial"):
                raise ValueError("Reference code/condition mismatch for " + key)
        elif ref.get("cover") is not None or ref.get("visibility") is not None:
            raise ValueError("Non-hand reference must not assign a hand condition")
        if ref.get("error") and presence != "error":
            raise ValueError("Reference error must not be reported as a definite label")
        if monitor.get("prediction") not in PREDICTIONS:
            raise ValueError("Invalid monitor prediction for " + key)
        if monitor.get("error") and monitor["prediction"] != "ERROR":
            raise ValueError("Monitor error must not become OBJECT/HUMAN")
        check_duration(ref, "reference")
        check_duration(monitor, "monitor")
        for field in ("run", "campaign", "image"):
            if not isinstance(meta.get(field), str) or not meta[field]:
                raise ValueError("Mapping requires nonempty " + field)
        image = PurePosixPath(meta["image"])
        if image.is_absolute() or ".." in image.parts or not image.parts or image.parts[0] != "frames":
            raise ValueError("Image path must remain under semantic_audit/frames")
        source = audit_root.joinpath(*image.parts).resolve(strict=True)
        if not source.is_relative_to(audit_root.resolve()):
            raise ValueError("Image symlink escapes semantic_audit")
        actual_sha = digest(source)
        if actual_sha != meta.get("sha256"):
            raise ValueError("Frozen mapping image hash mismatch for " + key)
        if actual_sha != ref.get("image_sha256"):
            raise ValueError("Reference image hash mismatch for " + key)
        if monitor.get("image_sha256") != ref["image_sha256"]:
            raise ValueError("Monitor/reference image hash mismatch for " + key)
        t = meta.get("container_time_s")
        if isinstance(t, bool) or not isinstance(t, (int, float)) or not math.isfinite(t) or t < 0:
            raise ValueError("Invalid container time for " + key)
        joined.append({"id": key, "run": meta["run"], "campaign": meta["campaign"],
                       "container_time_s": t, "image": "../../semantic_audit/" + quote(meta["image"], safe="/"),
                       "reference": ref, "monitor": monitor})
    return spec, joined


def fraction(numerator, denominator):
    return {"numerator": numerator, "denominator": denominator,
            "value": numerator / denominator if denominator else None}


def summarize(rows):
    """Every fraction carries its numerator and denominator; no accuracy fields."""
    matrix = {p: {v: 0 for v in PREDICTIONS} for p in PRESENCES}
    for row in rows:
        matrix[row["reference"]["presence"]][row["monitor"]["prediction"]] += 1
    total = len(rows)
    positive = sum(matrix["hand"].values())
    negative = sum(matrix["no_hand"].values())
    definite = positive + negative
    comparable = definite - matrix["hand"]["ERROR"] - matrix["no_hand"]["ERROR"]
    agree = matrix["hand"]["HUMAN"] + matrix["no_hand"]["OBJECT"]
    disagree = matrix["hand"]["OBJECT"] + matrix["no_hand"]["HUMAN"]
    uncertain = sum(matrix["uncertain"].values())
    reference_errors = sum(matrix["error"].values())
    monitor_errors_on_definite = matrix["hand"]["ERROR"] + matrix["no_hand"]["ERROR"]
    # Disjoint partition: reference uncertainty/errors take priority over monitor
    # outcomes. The independent monitor-error total is also reported explicitly.
    accounting = {"all_frames": total, "both_definite_and_successful": comparable,
                  "definite_reference_monitor_error": monitor_errors_on_definite,
                  "reference_uncertain_any_monitor": uncertain,
                  "reference_error_any_monitor": reference_errors}
    if comparable + monitor_errors_on_definite + uncertain + reference_errors != total:
        raise ValueError("Accounting failed")
    return {"frame_count": total, "run_count": len({r["run"] for r in rows}),
            "accounting_disjoint": accounting, "raw_contingency_reference_by_monitor": matrix,
            "reference_code_counts": dict(sorted(Counter(r["reference"]["code"] for r in rows).items())),
            "reference_definite_coverage": fraction(definite, total),
            "both_successful_definite_coverage": fraction(comparable, total),
            "reference_uncertain_fraction": fraction(uncertain, total),
            "reference_error_fraction": fraction(reference_errors, total),
            "monitor_error_fraction_all_frames": fraction(sum(r["monitor"]["prediction"] == "ERROR" for r in rows), total),
            "agreement_among_successful_definite_pairs": fraction(agree, comparable),
            "agreement_among_all_definite_reference_including_monitor_errors": fraction(agree, definite),
            "disagreement_among_successful_definite_pairs": fraction(disagree, comparable),
            "monitor_HUMAN_rate_among_model_reference_hand_including_monitor_errors": fraction(matrix["hand"]["HUMAN"], positive),
            "monitor_OBJECT_rate_among_model_reference_no_hand_including_monitor_errors": fraction(matrix["no_hand"]["OBJECT"], negative),
            "monitor_HUMAN_rate_among_model_reference_no_hand_including_monitor_errors": fraction(matrix["no_hand"]["HUMAN"], negative),
            "monitor_OBJECT_rate_among_model_reference_hand_including_monitor_errors": fraction(matrix["hand"]["OBJECT"], positive),
            "monitor_noncanonical_successful_responses": sum(r["monitor"]["prediction"] != "ERROR" and r["monitor"].get("strict_count") is None for r in rows),
            "reference_error_details": dict(Counter(str(r["reference"].get("error") or r["reference"]["code"]) for r in rows if r["reference"]["presence"] == "error")),
            "monitor_error_details": dict(Counter(str(r["monitor"].get("error") or "unspecified") for r in rows if r["monitor"]["prediction"] == "ERROR"))}


def stratified(rows, key):
    values = sorted({key(row) for row in rows})
    return {value: summarize([row for row in rows if key(row) == value]) for value in values}


def percentage(item):
    return "— (0/0)" if item["value"] is None else f'{100 * item["value"]:.2f}% ({item["numerator"]}/{item["denominator"]})'


METRICS = (
    ("پوشش برچسب قطعی مدل مرجع", "reference_definite_coverage"),
    ("پوشش جفت‌های قطعی بدون خطای اجرا", "both_successful_definite_coverage"),
    ("توافق در جفت‌های قطعی بدون خطای اجرا", "agreement_among_successful_definite_pairs"),
    ("توافق در همهٔ موارد قطعی مرجع؛ خطای مانیتور در مخرج", "agreement_among_all_definite_reference_including_monitor_errors"),
    ("پاسخ HUMAN مانیتور بین تصاویر دست‌دار به تشخیص مدل مرجع", "monitor_HUMAN_rate_among_model_reference_hand_including_monitor_errors"),
    ("پاسخ HUMAN مانیتور بین تصاویر بدون دست به تشخیص مدل مرجع", "monitor_HUMAN_rate_among_model_reference_no_hand_including_monitor_errors"),
    ("مرجع نامطمئن", "reference_uncertain_fraction"),
    ("خطای مرجع", "reference_error_fraction"),
    ("خطای مانیتور در همهٔ تصاویر", "monitor_error_fraction_all_frames"),
)


def build_report(run_dir):
    run_dir = Path(run_dir).resolve(strict=True)
    spec, rows = load_run(run_dir)
    summary = {"report_type": "automatic_cross_model_agreement", "independent_ground_truth_available": False,
               "scope": LIMIT, "scope_fa": LIMIT_FA,
               "input_hashes": {name: digest(run_dir / name) for name in ("spec.json", "frame_mapping.json", "reference.jsonl", "monitor.jsonl", "reference.sealed.json", "monitor.sealed.json")},
               "overall": summarize(rows),
               "by_campaign": stratified(rows, lambda r: r["campaign"]),
               "by_model_estimated_cover": stratified(rows, lambda r: r["reference"].get("cover") or "not_assigned"),
               "by_model_estimated_visibility": stratified(rows, lambda r: r["reference"].get("visibility") or "not_assigned"),
               "intervals": "No independent-frame confidence intervals are reported; frames share runs, an operator, and a session.",
               "run_spec": spec}
    (run_dir / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False, allow_nan=False) + "\n")
    overall = summary["overall"]
    metric_lines = [f"| {label} | {percentage(overall[key])} |" for label, key in METRICS]
    table_lines = [f'| {presence} | ' + " | ".join(str(overall["raw_contingency_reference_by_monitor"][presence][p]) for p in PREDICTIONS) + " |" for presence in PRESENCES]
    markdown = "\n".join([
        "# ممیزی خودکار توافق مدل‌ها", "", LIMIT_FA, "",
        f'همهٔ {len(rows)} فریم از {overall["run_count"]} اجرا در شمارش حفظ شده‌اند. این گزارش هیچ برچسب انسانی ایجاد نمی‌کند.', "",
        "## شاخص‌ها و مخرج‌ها", "", "| شاخص | مقدار و شمارش |", "|---|---|", *metric_lines, "",
        "در نرخ‌های مشروط بر مرجع، خطای مانیتور در مخرج باقی می‌ماند؛ مرجع نامطمئن/خطادار خارج از این مخرج‌ها اما جداگانه در شمارش کل نمایش داده می‌شود.", "",
        "## جدول کامل خروجی‌ها", "", "| برچسب مدل مرجع | HUMAN | OBJECT | ERROR |", "|---|---:|---:|---:|", *table_lines, "",
        "## محدودیت تفسیر", "",
        "- دستکش و پوشیدگی، دسته‌بندی خودکار هستند؛ تعداد آن‌ها شمارش تأییدشدهٔ انسانی نیست.",
        "- توافق و عدم‌توافق، جای دقت، حساسیت یا نرخ خطای تأییدشده را نمی‌گیرند.",
        "- OBJECT یعنی مانیتور دست تشخیص نداده است؛ به معنی ایمن‌بودن محیط نیست.",
        "- خروجی نامعتبر یا استثنا به‌صورت خطا حفظ می‌شود و برچسب «بدون دست» نمی‌گیرد.",
        "- فریم‌ها مستقل نیستند؛ برای درصدها فاصلهٔ اطمینان مبتنی بر استقلال فریم‌ها محاسبه نشده است.",
        "- نتیجهٔ نسخهٔ فعلی مدل روی فریم ویدیو، رأی تاریخیِ هنگام حرکت ربات یا زمان واکنش زنده نیست.", "",
        "تفکیک کامل بر اساس کمپین، پوشش و پوشیدگیِ تخمین‌زده‌شده در `summary.json` آمده است. گالری فقط خواندنی در `report.html` همهٔ خروجی‌ها و موارد اختلاف/ابهام/خطا را نشان می‌دهد.", "",
    ])
    (run_dir / "report_FA.md").write_text(markdown)
    cards = "".join(f'<article><span>{html.escape(label)}</span><strong dir="ltr">{html.escape(percentage(overall[key]))}</strong></article>' for label, key in METRICS)
    data = json.dumps(rows, ensure_ascii=False, allow_nan=False).replace("<", "\\u003c")
    document = """<!doctype html><html lang="fa" dir="rtl"><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>ممیزی خودکار توافق مدل‌ها</title>
<style>body{font:16px system-ui;margin:0;background:#f3f5f8;color:#182436}header,main{max-width:1180px;margin:auto;padding:24px}h1{font-size:26px}.warning{background:#fff3cc;border:1px solid #d7ad2e;padding:18px;line-height:1.9;border-radius:8px}.metrics{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:10px;margin:20px 0}.metrics article{background:white;padding:14px;border-radius:8px;display:flex;flex-direction:column;gap:8px}strong{font-size:22px}nav{display:flex;gap:10px;flex-wrap:wrap;align-items:center;margin:16px 0}button,select,input{font:inherit;padding:8px;max-width:100%}.gallery{display:grid;grid-template-columns:repeat(auto-fit,minmax(330px,1fr));gap:16px}.frame{background:white;border:1px solid #ccc;border-radius:8px;overflow:hidden}.frame img{display:block;width:100%;height:auto}.frame section{padding:12px}pre{white-space:pre-wrap;overflow-wrap:anywhere;font-size:12px;text-align:left;direction:ltr}small{color:#506078}.status{font-weight:bold;padding:6px;border-radius:4px;background:#e9edf4}.status.disagreement,.status.error{background:#ffe4db}.status.uncertain{background:#fff3cc}a{color:#1749a0}</style>
<header><h1>ممیزی خودکار توافق مدل‌ها — بدون برچسب انسانی</h1><div class="warning">__LIMIT__</div><p>گالری فقط خواندنی است؛ هیچ داده، ویدیو، برچسب انسانی یا مقاله‌ای را تغییر نمی‌دهد.</p><div class="metrics">__CARDS__</div><p><a href="summary.json">JSON کامل</a> · <a href="report_FA.md">گزارش فارسی</a> · <a href="spec.json">مشخصات ثابت اجرا</a></p></header>
<main><nav><label>نمایش <select id="kind"><option value="all">همهٔ تصاویر</option value="disagreement">اختلاف دو مدل</option><option value="agreement">توافق دو مدل</option><option value="uncertain">مرجع نامطمئن</option><option value="error">خطای اجرا/پاسخ</option></select></label><label>پوشش تخمین‌زده‌شده <select id="cover"><option value="all">همه</option><option value="glove">دستکش</option><option value="bare">بدون دستکش</option><option value="unspecified">نامشخص</option><option value="not_assigned">تعیین نشده</option></select></label><label>دید تخمین‌زده‌شده <select id="visibility"><option value="all">همه</option><option value="full">کامل</option><option value="partial">بخشی</option><option value="not_assigned">تعیین نشده</option></select></label><input id="search" type="search" placeholder="جست‌وجوی نام اجرا یا شناسه"><button id="prev">صفحهٔ قبل</button><button id="next">صفحهٔ بعد</button><span id="count"></span></nav><div class="gallery" id="gallery"></div></main>
<script>"use strict";
const rows=__ROWS__, pageSize=12; let page=0;
const byId=id=>document.getElementById(id);
function state(r){if(r.reference.presence==='error'||r.monitor.prediction==='ERROR')return 'error';if(r.reference.presence==='uncertain')return 'uncertain';return ((r.reference.presence==='hand')===(r.monitor.prediction==='HUMAN'))?'agreement':'disagreement';}
const words={agreement:'توافق؛ نه اثبات صحت',disagreement:'اختلاف دو مدل',uncertain:'مرجع نامطمئن',error:'خطای اجرا/پاسخ'};
function element(tag,text){const e=document.createElement(tag);if(text!==undefined)e.textContent=text;return e;}
function render(){const kind=byId('kind').value,cover=byId('cover').value,visibility=byId('visibility').value,q=byId('search').value.trim().toLowerCase();const filtered=rows.filter(r=>(kind==='all'||state(r)===kind)&&(cover==='all'||(r.reference.cover||'not_assigned')===cover)&&(visibility==='all'||(r.reference.visibility||'not_assigned')===visibility)&&(!q||(r.id+' '+r.run+' '+r.campaign).toLowerCase().includes(q)));const maxPage=Math.max(0,Math.ceil(filtered.length/pageSize)-1);page=Math.min(page,maxPage);byId('gallery').replaceChildren();byId('count').textContent=`${filtered.length} / ${rows.length} فریم — صفحهٔ ${page+1} / ${maxPage+1}`;byId('prev').disabled=page===0;byId('next').disabled=page===maxPage;for(const r of filtered.slice(page*pageSize,(page+1)*pageSize)){const card=element('article');card.className='frame';const im=element('img');im.src=r.image;im.alt='فریم واقعی ویدیو، '+r.id;im.loading='lazy';card.append(im);const body=element('section'),s=element('p',words[state(r)]);s.className='status '+state(r);body.append(s,element('p',r.run),element('small',`شناسه ${r.id} | ثانیهٔ فایل ${r.container_time_s.toFixed(3)} | ${r.campaign}`),element('p',`مدل مرجع: ${r.reference.code} / ${r.reference.presence} | پوشش: ${r.reference.cover||'—'} | دید: ${r.reference.visibility||'—'}`),element('p',`مانیتور: ${r.monitor.prediction}`));const details=element('details');details.append(element('summary','پاسخ‌های خام و خطاها'),element('pre',JSON.stringify({reference:r.reference,monitor:r.monitor},null,2)));body.append(details);card.append(body);byId('gallery').append(card);}}
for(const id of ['kind','cover','visibility','search'])byId(id).addEventListener('input',()=>{page=0;render();});byId('prev').addEventListener('click',()=>{page--;render();});byId('next').addEventListener('click',()=>{page++;render();});render();
</script></html>"""
    document = document.replace("__LIMIT__", html.escape(LIMIT_FA)).replace("__CARDS__", cards).replace("__ROWS__", data)
    (run_dir / "report.html").write_text(document)
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_dir", type=Path)
    args = parser.parse_args()
    result = build_report(args.run_dir)
    print(json.dumps({"frames": result["overall"]["frame_count"], "report": str(args.run_dir.resolve() / "report.html"),
                      "type": result["report_type"], "independent_ground_truth_available": False}, ensure_ascii=False))


if __name__ == "__main__":
    main()
