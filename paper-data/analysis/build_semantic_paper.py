"""Verified, offline paper tables from preserved human-review/replay records."""
from pathlib import Path
from math import comb
import json
from semantic_auto_report import digest, read_json
from semantic_human_review import validate_export, write_json

ROOT = Path(__file__).resolve().parent.parent
MERGED = ROOT / 'semantic_human_review/merged_2026-09-25_v1'


def finite_upper(N, n, alpha=.05):
    """Invert the exact SRS-without-replacement probability of zero positives."""
    denominator = comb(N, n)
    probabilities = [comb(N-k, n) / denominator if N-k >= n else 0.0 for k in range(N+1)]
    upper = max(k for k, p in enumerate(probabilities) if p >= alpha)
    return {'N': N, 'n': n, 'alpha': alpha, 'upper_K': upper,
            'p_zero_at_upper': probabilities[upper], 'p_zero_at_next': probabilities[upper+1]}


def build():
    provenance = read_json(MERGED / 'source_manifest.json')
    for name, expected in provenance['output_hashes'].items():
        assert digest(MERGED / name) == expected, name
    for info in provenance['sources'].values():
        assert digest(MERGED / info['preserved_copy']) == info['sha256']
    for name, expected in provenance['automatic_audit_hashes'].items():
        assert digest(MERGED / 'sources/automatic' / name) == expected
    for role in ('original', 'recheck'):
        validate_export(MERGED / 'sources' / (role+'.json'),
                        ROOT / 'semantic_human_review' / ('review_426_v1' if role=='original' else 'recheck_115_v1') / 'manifest.json', True)
    summary = read_json(MERGED / 'summary.json')
    counts = summary['merged_counts']
    assert counts['human_presence'] == {'hand':101, 'no_hand':322, 'uncertain':3}
    assert summary['rechecked_count'] == 115 and summary['label_changed_case_count'] == 32
    tables = counts['raw_unweighted_tables']
    m, q = tables['monitor'], tables['reference']
    rows = [
        ('Hand present', m['hand']['HUMAN'], m['hand']['OBJECT'], q['hand']['hand'], q['hand']['no_hand']),
        ('No visible hand', m['no_hand']['HUMAN'], m['no_hand']['OBJECT'], q['no_hand']['hand'], q['no_hand']['no_hand']),
        ('Uncertain', m['uncertain']['HUMAN'], m['uncertain']['OBJECT'], q['uncertain']['hand'], q['uncertain']['no_hand']),
    ]
    def write_table(name, columns, header, body, footer=''):
        text = (r'\begin{tabularx}{\linewidth}{' + columns + '}\n' + r'\toprule' + '\n' +
                header + '\n' + r'\midrule' + '\n' +
                '\n'.join(' & '.join(map(str,row)) + r'\\' for row in body) + '\n' +
                footer + r'\bottomrule' + '\n' + r'\end{tabularx}' + '\n')
        (ROOT/'analysis'/name).write_text(text)
    write_table('semantic_presence_rows.tex', 'Xrrrr',
                r'Human label & \multicolumn{2}{c}{FastVLM} & \multicolumn{2}{c}{Qwen reference}\\' + '\n' +
                r' & Hand & No hand & Hand & No hand\\', rows)
    condition_rows=[]
    for group, labels in [('by_human_hand_cover', [('bare','Bare hand'),('glove','Worn glove')]),
                          ('by_human_hand_visibility', [('full','At least one full hand'),('partial','Only partial hands')])]:
        for key, title in labels:
            c=summary[group][key]
            condition_rows.append((title,c['reviewed_frame_count'],c['unique_run_count'],
                                   c['raw_unweighted_tables']['monitor']['hand']['HUMAN'],
                                   c['raw_unweighted_tables']['reference']['hand']['hand']))
    write_table('semantic_condition_rows.tex', 'Xrrrr',
                r'Human condition & Frames & Runs & FastVLM hand & Qwen hand\\', condition_rows)
    strata=[]
    for key,title in [('disagreement','Model disagreement'),('both_positive','Both report hand'),('both_negative','Both report no hand')]:
        c=summary['by_stratum'][key]['human_presence']
        design=summary['original_sampling']
        strata.append((title,design['population_counts'][key],design['sample_counts'][key],
                       c.get('hand',0),c.get('no_hand',0),c.get('uncertain',0)))
    write_table('semantic_stratum_rows.tex', 'Xrrrrr',
                r'Stratum & Pool & Sample & Hand & No hand & Uncertain\\', strata,
                r'\midrule' + '\n' + r'Total &2158&426&101&322&3\\' + '\n')
    negative=summary['by_stratum']['both_negative']['human_presence']
    assert negative == {'no_hand':300}
    bound=finite_upper(2032,300)
    assert bound['upper_K']==18 and bound['p_zero_at_upper']>=.05>bound['p_zero_at_next']
    result={'source_summary_sha256':digest(MERGED/'summary.json'), 'human_counts':counts['human_presence'],
            'reviewed_frames':426,'reviewed_runs':counts['unique_run_count'],'rechecked_frames':115,
            'raw_tables':tables,'condition_rows':condition_rows,'stratum_rows':strata,
            'negative_stratum_conditional_bound':bound,
            'bound_scope':'Finite fixed 2032-frame stratum under recorded SRS design and correct human labels only; not a live, session-generalization or physical-risk bound.',
            'zero_observed_FN_is_not_perfect_recall':True}
    write_json(ROOT/'analysis/semantic_paper_results.json',result)
    products=['semantic_presence_rows.tex','semantic_condition_rows.tex','semantic_stratum_rows.tex','semantic_paper_results.json']
    write_json(ROOT/'analysis/semantic_paper_manifest.json',{'builder_sha256':digest(__file__),
        'source_manifest_sha256':digest(MERGED/'source_manifest.json'),
        'outputs':{p:digest(ROOT/'analysis'/p) for p in products}})
    print(json.dumps(result,indent=2))


if __name__=='__main__':
    build()
