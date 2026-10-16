#!/usr/bin/env python3
"""Read-only eligibility/replay report for learning.json audit exports (no DB)."""
from __future__ import annotations

import argparse
import json
import os
import platform
import resource
import statistics
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from time import perf_counter

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
from app.services.learning_analytics.ml_features import (  # noqa: E402
    MLFeatureRow, build_quiz_features, build_video_features, fingerprint, utc, unique_reference_rows, video_identity, video_outline,
)
from app.services.learning_analytics.ml_anomaly import result_key, score_cohorts  # noqa: E402


def table(audit, name):
    payload = audit.get('tables', {}).get(name, {})
    return payload.get('rows', []) if isinstance(payload, dict) else []


def evaluate_audits(audits: list[dict]) -> dict:
    started = perf_counter()
    official = [table(a, 'academic_student_learning_snapshots') for a in audits]
    before = fingerprint(official)
    selected = {}
    for a in audits:
        if a.get('class', {}).get('id') and a.get('course_id'):
            key = a['class']['id']
            if key not in selected or str(a.get('generated_at_utc', '')) > str(selected[key].get('generated_at_utc', '')):
                selected[key] = a
    skipped = {'video': Counter(), 'quiz': Counter()}
    rows, roster_people, rules, comparisons = [], set(), {}, {}
    quality = Counter()
    for a in selected.values():
        course = a['course_id']
        first_row = len(rows)
        cutoff = utc(a.get('generated_at_utc'))
        if not cutoff:
            quality['invalid_export_time'] += 1
            continue
        identities = defaultdict(set)
        for student in a.get('roster', []):
            if student.get('username') and student.get('active', True):
                identities[student['username']].add(student.get('id') or student.get('student_code'))
        users = {name for name, ids in identities.items() if len(ids) == 1}
        quality['ambiguous_identities'] += len(identities)-len(users)
        roster_people.update(users)
        bounded = {}
        for name in ['analytics_course_sessions', 'analytics_student_video_progress', 'analytics_quiz_attempts',
                     'analytics_quiz_item_submissions', 'analytics_learning_behavior_snapshots']:
            source = table(a, name)
            bounded[name] = [r for r in source if r.get('course_id') == course
                and (not r.get('username') or r['username'] in users)]
            quality['out_of_scope_rows'] += len(source)-len(bounded[name])
        outlines = [s for s in bounded['analytics_course_sessions'] if s.get('active', True)]
        outline, current_videos = video_outline(outlines)
        aliases = {item['usage_key']: item['metadata']['parent_block_id'] for s in outlines
            for item in (s.get('components_json') or {}).get('components', [])
            if item.get('usage_key') and '+type@vertical+' in str((item.get('metadata') or {}).get('parent_block_id', ''))
            and item.get('block_type') in {'problem', 'quiz', 'itembank', 'library_content'}}
        videos, attempts, items = defaultdict(list), defaultdict(list), defaultdict(list)
        for v in bounded['analytics_student_video_progress']:
            if video_identity(v.get('video_id')) in current_videos:
                videos[v['username']].append(v)
        for v in bounded['analytics_quiz_attempts']:
            attempts[(v['username'], aliases.get(v['unit_usage_key'], v['unit_usage_key']))].append(v)
        for v in bounded['analytics_quiz_item_submissions']:
            items[v.get('attempt_id')].append(v)
        truncated = {name for name, data in a.get('tables', {}).items() if isinstance(data, dict) and data.get('truncated')}
        for user in sorted(users):
            if truncated & {'analytics_course_sessions', 'analytics_student_video_progress'}:
                skipped['video']['TRUNCATED_SOURCE'] += 1
            else:
                build = build_video_features(subject_key=user, course_id=course, outline_fingerprint=outline,
                    videos=videos[user], cutoff=cutoff)
                if build.row:
                    rows.append(build.row)
                else:
                    skipped['video'].update(build.reasons or ['NO_MEASURED_ACTIVITY'])
        for (user, unit), history in sorted(attempts.items()):
            if truncated & {'analytics_course_sessions', 'analytics_quiz_attempts', 'analytics_quiz_item_submissions'}:
                skipped['quiz']['TRUNCATED_SOURCE'] += 1
                continue
            build, first_by_cohort = None, {}
            for attempt in sorted(history, key=lambda r: (utc(r.get('started_at')) or datetime.max, r.get('attempt_no') or 0, str(r.get('id')))):
                current = build_quiz_features(subject_key=user, course_id=course, unit_usage_key=unit,
                    attempt=attempt, items=items[attempt.get('id')], cutoff=cutoff)
                if build is None or current.row:
                    build = current
                if current.row:
                    first_by_cohort.setdefault(current.row.cohort_key, current.row)
            if first_by_cohort:
                rows.extend(first_by_cohort.values())
            else:
                skipped['quiz'].update(build.reasons or ['NO_MEASURED_ACTIVITY'])
        for r in bounded['analytics_learning_behavior_snapshots']:
            if r.get('class_id', a['class']['id']) == a['class']['id']:
                rules[(a['class']['id'], course, r.get('username'))] = r.get('classification')
        for r in rows[first_row:]:
            if r.family == 'video':
                comparisons[(a['class']['id'], result_key(r))] = rules.get((a['class']['id'], course, r.subject_key))
    unique = unique_reference_rows(rows)
    scores = score_cohorts(unique)
    distribution, group_ids = defaultdict(list), set()
    disagreement = Counter(compared=0, different=0)
    # Count disagreement descriptively; rules are not ground-truth labels.
    for r in unique:
        score = scores[result_key(r)]
        if score['status'] == 'SCORED':
            group_ids.add((r.family, r.cohort_key))
            distribution[r.family].append(score['reference_percentile'])
        else:
            skipped[r.family].update(score.get('reason_codes') or ['UNSCORED'])
    for (_, key), rule in comparisons.items():
        score = scores[key]
        if score['status'] == 'SCORED' and rule:
            disagreement['compared'] += 1
            disagreement['different'] += int(score['outlier'] != (rule in {'POSSIBLE_ANOMALY', 'POSSIBLE_CHEATING'}))
    return {'schema_version': 1, 'class_exports': len(selected), 'roster_students': len(roster_people),
        'eligibility_counts': {family: sum(r.family == family for r in unique) for family in ('video', 'quiz')},
        'skipped_by_reason': {k: dict(v) for k, v in skipped.items()}, 'scored_groups': len(group_ids),
        'scored_students': {k: len(distribution[k]) for k in ('video', 'quiz')},
        'score_distribution': {k: {'min_percentile': min(v), 'median_percentile': statistics.median(v),
            'max_percentile': max(v)} for k, v in distribution.items() if v},
        'rule_ml_disagreement': dict(disagreement), 'accuracy': {'status': 'UNMEASURED_NO_LABELS'},
        'duplicate_student_checks': {'duplicate_exports': sum(bool(a.get('class', {}).get('id') and a.get('course_id')) for a in audits)-len(selected),
            'duplicate_eligible_rows': len(rows)-len(unique)}, 'source_quality': dict(quality),
        'official_hash_before_after': {'before': before, 'after': fingerprint(official)},
        'latency_seconds': round(perf_counter()-started, 4), 'runtime_versions': runtime_versions()}


def runtime_versions():
    import numpy
    import sklearn
    return {'python': platform.python_version(), 'numpy': numpy.__version__, 'scikit_learn': sklearn.__version__}


def benchmark(size: int) -> dict:
    # Run each size in a fresh process to include first-import memory honestly.
    before = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    started = perf_counter()
    rows = [MLFeatureRow(str(i), 'video', 'benchmark', {
        'completion_watch_gap': (i % 19)/20, 'watch_ratio': .1+(i % 29)/40,
        'seeks_per_watch_minute': (i % 11)/10, 'passive_ratio': (i % 13)/20}, datetime(2026,10,9)) for i in range(size)]
    scores = score_cohorts(rows)
    elapsed = perf_counter()-started
    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    rss_mib = (peak-before)/1024
    return {'rows': size, 'trees': 100, 'scored': sum(s['status']=='SCORED' for s in scores.values()),
        'elapsed_seconds': round(elapsed, 4), 'incremental_peak_rss_mib': round(rss_mib, 2),
        'provisional_budget_met': elapsed < 10 and rss_mib < 256,
        'environment': {'platform': platform.platform(), 'logical_cpus': os.cpu_count()},
        'runtime_versions': runtime_versions(), 'synthetic_only': True}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--audit', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--seed', type=int, choices=[42], default=42)
    parser.add_argument('--benchmark', type=int, choices=[1000,5000])
    args = parser.parse_args()
    if args.benchmark:
        report = benchmark(args.benchmark)
    else:
        if not args.audit:
            parser.error('--audit is required unless --benchmark is used')
        paths = [args.audit] if args.audit.is_file() else sorted(args.audit.rglob('learning.json'))
        if not paths:
            parser.error('No learning.json files found')
        if args.output.resolve() in {p.resolve() for p in paths}:
            parser.error('Output must differ from every input export')
        report = evaluate_audits([json.loads(path.read_text()) for path in paths])
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False)+'\n')
    print(json.dumps({'output': str(args.output), 'scored_groups': report.get('scored_groups'),
        'scored': report.get('scored_students', report.get('scored'))}))


if __name__ == '__main__':
    main()
