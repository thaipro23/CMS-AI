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


def export_quiz_aliases(sessions):
    return {item['usage_key']:item['metadata']['parent_block_id'] for session in sessions
        for item in (session.get('components_json') or {}).get('components',[])
        if item.get('usage_key') and '+type@vertical+' in str((item.get('metadata') or {}).get('parent_block_id',''))
        and item.get('block_type') in {'problem','quiz','itembank','library_content'}}


def _legacy_diagnostics(audits: list[dict]) -> dict:
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
        aliases = export_quiz_aliases(outlines)
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


def evaluate_audits(audits: list[dict], *, include_quiz: bool = False, seed: int = 42) -> dict:
    """Pool the explicitly supplied exports; never fabricate historical playback."""
    started = perf_counter()
    official = [table(a, 'academic_student_learning_snapshots') for a in audits]
    before = fingerprint(official)
    selected = {}
    for audit in audits:
        key = audit.get('class',{}).get('id')
        if key and audit.get('course_id') and (key not in selected or
                str(audit.get('generated_at_utc','')) > str(selected[key].get('generated_at_utc',''))):
            selected[key] = audit
    videos, people_ids, outlines = defaultdict(dict), defaultdict(set), {}
    cutoffs, truncated_users, quiz_groups = [], set(), set()
    latest, inconsistent_courses, inconsistent_users = {}, set(), set()
    for audit in selected.values():
        when = utc(audit.get('generated_at_utc'))
        if when is None:
            continue
        course = audit['course_id']
        sessions = [s for s in table(audit,'analytics_course_sessions')
            if s.get('course_id') == course and s.get('active',True)]
        outline, identities = video_outline(sessions)
        old = latest.get(course)
        if old is None or when > old['time']:
            latest[course] = {'time':when,'outline':outline,'identities':identities,'sessions':sessions,
                'truncated':bool((audit.get('tables',{}).get('analytics_course_sessions') or {}).get('truncated'))}
            inconsistent_courses.discard(course)
        elif when == old['time'] and outline != old['outline']:
            inconsistent_courses.add(course)
    quality = Counter()
    for audit in selected.values():
        cutoff = utc(audit.get('generated_at_utc'))
        if cutoff is None:
            quality['invalid_export_time'] += 1
            continue
        cutoffs.append(cutoff)
        course = audit['course_id']
        users = set()
        for student in audit.get('roster',[]):
            if student.get('username') and student.get('active',True):
                user = student['username']
                people_ids[user].add(student.get('id') or student.get('student_code'))
                users.add(user)
        current = latest[course]
        sessions, outline, identities = current['sessions'],current['outline'],current['identities']
        aliases = export_quiz_aliases(sessions)
        outlines[course] = outline
        if course in inconsistent_courses:
            inconsistent_users.update(users)
        truncated = current['truncated'] or bool((audit.get('tables',{}).get('analytics_student_video_progress') or {}).get('truncated'))
        if truncated:
            truncated_users.update(users)
        for video in table(audit,'analytics_student_video_progress'):
            user = video.get('username')
            if video.get('course_id') != course or user not in users:
                quality['out_of_scope_rows'] += 1
                continue
            identity = video_identity(video.get('video_id'))
            if identity not in identities:
                continue
            key = fingerprint([course,identity])
            previous = videos[user].get(key)
            if previous is None or str(video.get('last_event_at','')) > str(previous.get('last_event_at','')):
                videos[user][key] = {**video,'video_id':key}
        for attempt in table(audit,'analytics_quiz_attempts'):
            if attempt.get('course_id') == course and attempt.get('username') in users:
                unit = attempt.get('unit_usage_key')
                quiz_groups.add((course,attempt['username'],aliases.get(unit,unit)))
            else:
                quality['out_of_scope_rows'] += 1
    ambiguous = {u for u, ids in people_ids.items() if len(ids) != 1 or None in ids}
    quality['ambiguous_identities'] = len(ambiguous)
    skipped = {'video':Counter(),'quiz':Counter()}
    rows = []
    cutoff = max(cutoffs) if cutoffs else None
    for user in sorted(people_ids):
        if user in ambiguous:
            skipped['video']['AMBIGUOUS_IDENTITY'] += 1
        elif user in inconsistent_users:
            skipped['video']['INCONSISTENT_COURSE_OUTLINE'] += 1
        elif user in truncated_users:
            skipped['video']['TRUNCATED_SOURCE'] += 1
        else:
            build = build_video_features(subject_key=user,course_id='export-pool',
                outline_fingerprint=fingerprint(outlines) if any(outlines.values()) else '',
                reference_scope=fingerprint(sorted(outlines)), videos=list(videos[user].values()),cutoff=cutoff)
            if build.row:
                rows.append(build.row)
            else:
                skipped['video'].update(build.reasons or ['NO_MEASURED_ACTIVITY'])
    scores = score_cohorts(rows,seed=seed)
    groups = defaultdict(list)
    for row in rows:
        groups[row.cohort_key].append(row)
    skipped_groups = []
    for key, members in groups.items():
        result = scores[result_key(members[0])]
        if result['status'] != 'SCORED':
            skipped_groups.append({'family':'video','cohort_digest':key,
                'reference_count':result['reference_count'],'reason_codes':result['reason_codes']})
    if skipped['video']:
        skipped_groups.append({'family':'video','cohort_digest':None,
            'description':'Không đủ dữ liệu để tạo nhóm video', 'reason_counts':dict(skipped['video'])})
    scored = [s for s in scores.values() if s['status']=='SCORED']
    for s in scores.values():
        if s['status'] != 'SCORED':
            skipped['video'].update(s['reason_codes'])
    quiz_count, quiz_scored, quiz_distribution = 0, 0, None
    if include_quiz:
        legacy = _legacy_diagnostics(audits)
        quiz_count = legacy['eligibility_counts']['quiz']
        quiz_scored = legacy['scored_students']['quiz']
        skipped['quiz'].update(legacy['skipped_by_reason']['quiz'])
        quiz_distribution = legacy['score_distribution'].get('quiz')
    elif quiz_groups:
        skipped['quiz']['QUIZ_ML_DISABLED'] = len(quiz_groups)
        skipped_groups.append({'family':'quiz','cohort_digest':None,'learner_units':len(quiz_groups),
            'reason_codes':['QUIZ_ML_DISABLED']})
    distribution = {}
    if scored:
        values = [s['reference_percentile'] for s in scored]
        distribution['video'] = {'min_percentile':min(values),'median_percentile':statistics.median(values),
            'max_percentile':max(values)}
    if quiz_distribution:
        distribution['quiz'] = quiz_distribution
    return {'schema_version':2,'class_exports':len(selected),'roster_students':len(people_ids),
        'eligibility_counts':{'video':len(rows),'quiz':quiz_count},
        'skipped_by_reason':{k:dict(v) for k,v in skipped.items()},'skipped_groups':skipped_groups,
        'scored_groups':sum(scores[result_key(m[0])]['status']=='SCORED' for m in groups.values()),
        'scored_students':{'video':len(scored),'quiz':quiz_scored},'score_distribution':distribution,
        'confidence_counts':dict(Counter(s['confidence'] for s in scored)),
        'comparison_summary':dict(Counter(s['comparison_status'] for s in scored)),
        'rule_ml_disagreement':{'compared':0,'different':0,'status':'RELATIVE_RANK_ONLY'},
        'accuracy':{'status':'UNMEASURED_NO_LABELS'},
        'duplicate_student_checks':{'duplicate_exports':sum(bool(a.get('class',{}).get('id') and a.get('course_id')) for a in audits)-len(selected),
            'duplicate_eligible_rows':0},'source_quality':dict(quality),
        'official_hash_before_after':{'before':before,'after':fingerprint(official)},
        'latency_seconds':round(perf_counter()-started,4),'runtime_versions':runtime_versions()}


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
    return {'rows': size, 'trees': 200, 'primary_method':'median_mad', 'scored': sum(s['status']=='SCORED' for s in scores.values()),
        'elapsed_seconds': round(elapsed, 4), 'incremental_peak_rss_mib': round(rss_mib, 2),
        'provisional_budget_met': elapsed < 10 and rss_mib < 256,
        'environment': {'platform': platform.platform(), 'logical_cpus': os.cpu_count()},
        'runtime_versions': runtime_versions(), 'synthetic_only': True}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--audit', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--seed', type=int, default=42)
    parser.add_argument('--include-quiz', action='store_true', help='Offline provenance diagnosis only; runtime quiz ML stays disabled')
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
        report = evaluate_audits([json.loads(path.read_text()) for path in paths],include_quiz=args.include_quiz,seed=args.seed)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False)+'\n')
    print(json.dumps({'output': str(args.output), 'scored_groups': report.get('scored_groups'),
        'scored': report.get('scored_students', report.get('scored'))}))


if __name__ == '__main__':
    main()
