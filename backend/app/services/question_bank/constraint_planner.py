from __future__ import annotations

import re
from collections import defaultdict
from typing import Any

from app.models.question import Question
from app.models.question_bank import QuestionBankRelease
from app.services.openedx_exporter import _build_problem_display_name, is_manually_authored_question
from app.services.question_family import normalize_difficulty
from app.services.question_bank.helpers import _ui_notice

DIFFS = ("easy", "medium", "hard")
QTYPES = ("single_select", "multi_select", "dropdown_fill", "text_input", "numerical_input")


def canonical_question_type(value: Any) -> str:
    raw = str(value or "").strip().lower().replace("-", "_").replace(" ", "_")
    return {
        "single": "single_select", "single_choice": "single_select", "single_select": "single_select",
        "multiple_choice": "multi_select", "multiple_select": "multi_select",
        "multi_choice": "multi_select", "multi_select": "multi_select",
        "dropdown_fill": "dropdown_fill", "select_fill": "dropdown_fill", "fill_dropdown": "dropdown_fill",
        "text": "text_input", "text_input": "text_input",
        "numerical": "numerical_input", "numeric": "numerical_input", "numerical_input": "numerical_input",
    }.get(raw, raw or "unknown")


def _is_legacy(question: Question) -> bool:
    return str(getattr(question, "source_type", "") or "").strip().lower() == "legacy_quiz_excel"


def _legacy_unclassified(question: Question) -> bool:
    if not _is_legacy(question):
        return False
    flags = {str(x or "").strip().lower() for x in (getattr(question, "quality_flags", None) or [])}
    if "legacy_import_unclassified_difficulty" in flags:
        return True
    evidence = str(getattr(question, "source_evidence", "") or "").replace(" ", "").lower()
    return '"difficulty_classified":false' in evidence


def _targets(total: int, weights: dict[str, int], order: tuple[str, ...]) -> dict[str, int]:
    total = max(0, int(total or 0))
    clean = {key: max(0, int(weights.get(key, 0) or 0)) for key in order}
    weight_sum = sum(clean.values())
    if total and weight_sum <= 0:
        raise ValueError("Cấu hình phân bổ đang bật nhưng tổng tỷ lệ bằng 0%.")
    raw = {key: (total * clean[key] / weight_sum if weight_sum else 0) for key in order}
    result = {key: int(raw[key]) for key in order}
    remaining = total - sum(result.values())
    for key in sorted(
        order,
        key=lambda item: (raw[item] - result[item], order.index(item)),
        reverse=True,
    ):
        if remaining <= 0:
            break
        result[key] += 1
        remaining -= 1
    return result


def _diff_targets(total: int, easy: int, medium: int, hard: int, enabled: bool) -> dict[str, int]:
    if not enabled:
        return {"any": int(total)}
    return _targets(total, {"easy": easy, "medium": medium, "hard": hard}, DIFFS)


def _type_targets(total: int, config: dict[str, Any]) -> dict[str, int]:
    if not bool(config.get("question_type_enabled")):
        return {"auto": int(total)}
    weights = config.get("question_type_weights") or {}
    return _targets(total, {key: int(weights.get(key, 0) or 0) for key in QTYPES}, QTYPES)


def _prepare_entries(
    workflow,
    releases: list[QuestionBankRelease],
    *,
    difficulty_enabled: bool,
    question_type_enabled: bool,
    final_test: bool,
) -> tuple[list[dict], dict[str, int]]:
    entries: list[dict] = []
    source_counts = {str(release.id): 0 for release in releases}
    seen_questions: set[str] = set()
    seen_components: set[str] = set()
    invalid: list[str] = []

    for release in releases:
        if release.status != "published" or not release.openedx_library_key:
            raise ValueError(f"Release {release.release_code or release.id} chưa published đầy đủ.")
        if not bool((release.metadata_json or {}).get("verification_complete")):
            raise ValueError(f"Release {release.release_code or release.id} chưa verify đầy đủ trên Open edX.")
        rows, questions = workflow._published_release_question_rows(release)
        for row in rows:
            question = questions[row.question_id]
            if final_test:
                reasons: list[str] = []
                if question.status not in {"approved", "published"}:
                    reasons.append(f"status={question.status}")
                if bool(question.is_retired):
                    reasons.append("retired")
                if bool(question.is_duplicate):
                    reasons.append("duplicate")
                if reasons:
                    preview = re.sub(r"\s+", " ", str(question.question_text or "")).strip()[:100]
                    invalid.append(f"{question.id} · {preview} · {', '.join(reasons)}")
                    continue

            component = str(row.openedx_library_problem_id or "").strip().strip("\"'")
            if not component:
                raise ValueError(f"Release question {row.question_id} chưa có Open edX Library component.")
            if str(question.id) in seen_questions or component in seen_components:
                continue
            seen_questions.add(str(question.id))
            seen_components.add(component)
            entries.append({
                "release_id": str(release.id),
                "release": release,
                "question": question,
                "component": component,
                "difficulty": (
                    "flex"
                    if difficulty_enabled and _legacy_unclassified(question)
                    else normalize_difficulty(row.difficulty or question.difficulty)
                    if difficulty_enabled
                    else "any"
                ),
                "question_type": canonical_question_type(question.question_type) if question_type_enabled else "auto",
                "flex": False,
            })
            source_counts[str(release.id)] += 1

    if invalid:
        sample = " | ".join(invalid[:20])
        suffix = " | ..." if len(invalid) > 20 else ""
        raise ValueError(f"Final test gặp {len(invalid)} câu không còn hợp lệ: {sample}{suffix}")
    return entries, source_counts


def _assign_flexible(entries: list[dict], requested: dict[str, int]) -> None:
    current = {difficulty: 0 for difficulty in DIFFS}
    flexible: list[dict] = []
    for entry in entries:
        if entry["difficulty"] == "flex":
            flexible.append(entry)
        elif entry["difficulty"] in current:
            current[entry["difficulty"]] += 1

    for entry in flexible:
        deficits = {difficulty: max(0, requested.get(difficulty, 0) - current[difficulty]) for difficulty in DIFFS}
        choices = [difficulty for difficulty in DIFFS if deficits[difficulty] > 0] or list(DIFFS)
        chosen = max(
            choices,
            key=lambda difficulty: (deficits[difficulty], -current[difficulty], -DIFFS.index(difficulty)),
        )
        entry["difficulty"] = chosen
        entry["flex"] = True
        current[chosen] += 1


def _rebalance_legacy(requested: dict[str, int], capacity: dict[str, int], total: int) -> dict[str, int]:
    result = {
        difficulty: min(requested.get(difficulty, 0), capacity.get(difficulty, 0))
        for difficulty in DIFFS
    }
    remaining = int(total) - sum(result.values())
    while remaining > 0:
        choices = [difficulty for difficulty in DIFFS if result[difficulty] < capacity.get(difficulty, 0)]
        if not choices:
            break
        chosen = min(
            choices,
            key=lambda difficulty: (
                result[difficulty] / max(requested.get(difficulty, 0), 1),
                DIFFS.index(difficulty),
            ),
        )
        result[chosen] += 1
        remaining -= 1
    if remaining:
        raise ValueError(
            f"Không đủ dữ liệu để tạo Quiz: cần {total} câu, hiện có {sum(capacity.values())}."
        )
    return result


def _pair_targets(
    entries: list[dict],
    *,
    total: int,
    easy: int,
    medium: int,
    hard: int,
    config: dict[str, Any],
) -> tuple[dict[tuple[str, str], int], dict[str, int], dict[str, int], list[str], bool]:
    difficulty_enabled = bool(config.get("difficulty_enabled", True))
    question_type_enabled = bool(config.get("question_type_enabled", False))
    requested_diff = _diff_targets(total, easy, medium, hard, difficulty_enabled)
    requested_types = _type_targets(total, config)
    all_legacy = bool(entries) and all(_is_legacy(entry["question"]) for entry in entries)
    warnings: list[str] = []

    if difficulty_enabled:
        _assign_flexible(entries, requested_diff)

    capacity: dict[tuple[str, str], int] = defaultdict(int)
    for entry in entries:
        capacity[(entry["difficulty"], entry["question_type"])] += 1

    if not difficulty_enabled and not question_type_enabled:
        if len(entries) < total:
            raise ValueError(f"Không đủ dữ liệu để tạo Quiz: cần {total} câu, hiện có {len(entries)}.")
        return {("any", "auto"): total}, requested_diff, requested_types, warnings, all_legacy

    if difficulty_enabled and not question_type_enabled:
        diff_capacity = {difficulty: capacity.get((difficulty, "auto"), 0) for difficulty in DIFFS}
        effective = _rebalance_legacy(requested_diff, diff_capacity, total) if all_legacy else dict(requested_diff)
        if not all_legacy:
            missing = [difficulty for difficulty in DIFFS if diff_capacity[difficulty] < requested_diff[difficulty]]
            if missing:
                raise ValueError(
                    "Không đủ câu theo độ khó: "
                    + ", ".join(
                        f"{difficulty} cần {requested_diff[difficulty]}, có {diff_capacity[difficulty]}"
                        for difficulty in missing
                    )
                )
        elif effective != requested_diff:
            warnings.append(
                "Kho legacy thiếu một mức độ; hệ thống đã phân phần thiếu sang mức còn câu và vẫn giữ đủ tổng số câu."
            )
        return (
            {(difficulty, "auto"): count for difficulty, count in effective.items() if count > 0},
            effective,
            requested_types,
            warnings,
            all_legacy,
        )

    if not difficulty_enabled and question_type_enabled:
        for question_type, needed in requested_types.items():
            available = capacity.get(("any", question_type), 0)
            if available < needed:
                raise ValueError(f"Không đủ câu định dạng {question_type}: cần {needed}, có {available}.")
        return (
            {("any", question_type): count for question_type, count in requested_types.items() if count > 0},
            requested_diff,
            requested_types,
            warnings,
            all_legacy,
        )

    pair_targets: dict[tuple[str, str], int] = defaultdict(int)
    remaining_diff = dict(requested_diff)
    type_order = sorted(
        [question_type for question_type in QTYPES if requested_types.get(question_type, 0) > 0],
        key=lambda question_type: (
            sum(capacity.get((difficulty, question_type), 0) for difficulty in DIFFS)
            - requested_types[question_type]
        ),
    )
    for question_type in type_order:
        for _ in range(requested_types[question_type]):
            choices = [
                difficulty
                for difficulty in DIFFS
                if pair_targets[(difficulty, question_type)] < capacity.get((difficulty, question_type), 0)
            ]
            if not choices:
                raise ValueError(f"Không đủ câu định dạng {question_type}: cần {requested_types[question_type]}.")
            chosen = max(
                choices,
                key=lambda difficulty: (
                    remaining_diff.get(difficulty, 0) > 0,
                    remaining_diff.get(difficulty, 0),
                    capacity.get((difficulty, question_type), 0) - pair_targets[(difficulty, question_type)],
                    -DIFFS.index(difficulty),
                ),
            )
            pair_targets[(chosen, question_type)] += 1
            if remaining_diff.get(chosen, 0) > 0:
                remaining_diff[chosen] -= 1

    effective = {
        difficulty: sum(pair_targets.get((difficulty, question_type), 0) for question_type in QTYPES)
        for difficulty in DIFFS
    }
    if not all_legacy and effective != requested_diff:
        raise ValueError(
            "Không đủ câu để đồng thời đáp ứng chính xác Độ khó và Định dạng đã chọn. "
            "Hãy giảm số câu hoặc điều chỉnh tỷ lệ."
        )
    if all_legacy and effective != requested_diff:
        warnings.append(
            "Kho legacy không đủ đúng ma trận Độ khó × Định dạng; giữ đúng định dạng và phân lại độ khó sang mức còn câu."
        )
    return (
        {key: value for key, value in pair_targets.items() if value > 0},
        effective,
        requested_types,
        warnings,
        all_legacy,
    )


def _display_names(entries: list[dict]) -> dict[str, str]:
    return {
        entry["component"]: _build_problem_display_name(entry["question"])
        for entry in entries
        if is_manually_authored_question(entry["question"])
    }


def _slot(
    no: int,
    entries: list[dict],
    pick: int,
    pair: tuple[str, str],
    release,
    chapter_title: str = "",
) -> dict:
    return {
        "slot_no": no,
        "difficulty": "ANY" if pair[0] == "any" else pair[0].upper(),
        "question_type": pair[1],
        "pick_count": int(pick),
        "max_count": int(pick),
        "library_key": release.openedx_library_key,
        "openedx_problem_ids": [entry["component"] for entry in entries],
        "problem_display_names": _display_names(entries),
        "question_ids": [str(entry["question"].id) for entry in entries],
        "families": [],
        "family_names": [chapter_title] if chapter_title else [],
        "variant_count": len(entries),
        "sampling_strategy": "constraint_pool",
        "source_release_id": release.id,
        "source_release_code": release.release_code,
        "source_chapter_title": chapter_title or None,
        "rule": f"random {pick}/{len(entries)}",
    }


def _common_plan_meta(entries: list[dict], config: dict[str, Any], all_legacy: bool) -> dict:
    difficulty_enabled = bool(config.get("difficulty_enabled", True))
    question_type_enabled = bool(config.get("question_type_enabled", False))
    return {
        "difficulty_enabled": difficulty_enabled,
        "question_type_enabled": question_type_enabled,
        "difficulty_policy": (
            "disabled_random_from_total"
            if not difficulty_enabled
            else "legacy_rebalance_when_capacity_short"
            if all_legacy
            else "strict_native"
        ),
        "question_type_policy": "quota" if question_type_enabled else "disabled_random_from_total",
        "unclassified_difficulty_question_count": sum(1 for entry in entries if entry.get("flex")),
        "flexibly_assigned_question_count": sum(1 for entry in entries if entry.get("flex")),
    }


def build_release_constraint_plan(
    workflow,
    *,
    release,
    total_questions: int,
    difficulty_easy: int,
    difficulty_medium: int,
    difficulty_hard: int,
    max_families_per_bank: int = 2,
    config: dict[str, Any],
) -> dict:
    del max_families_per_bank
    entries, source_counts = _prepare_entries(
        workflow,
        [release],
        difficulty_enabled=bool(config.get("difficulty_enabled", True)),
        question_type_enabled=bool(config.get("question_type_enabled", False)),
        final_test=False,
    )
    pair_targets, effective_diff, type_targets, warnings, all_legacy = _pair_targets(
        entries,
        total=total_questions,
        easy=difficulty_easy,
        medium=difficulty_medium,
        hard=difficulty_hard,
        config=config,
    )
    by_pair: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for entry in entries:
        by_pair[(entry["difficulty"], entry["question_type"])].append(entry)

    slots: list[dict] = []
    coverage: list[dict] = []
    for pair, target in pair_targets.items():
        candidates = by_pair.get(pair, [])
        if len(candidates) < target:
            raise ValueError(
                f"Không đủ câu cho nhóm {pair[0]} × {pair[1]}: cần {target}, có {len(candidates)}."
            )
        slots.append(_slot(len(slots) + 1, candidates, target, pair, release))
        coverage.append({
            "difficulty": "ANY" if pair[0] == "any" else pair[0].upper(),
            "question_type": pair[1],
            "target_questions": target,
            "candidate_questions": len(candidates),
            "selected_slots": 1,
        })

    requested = _diff_targets(
        total_questions,
        difficulty_easy,
        difficulty_medium,
        difficulty_hard,
        bool(config.get("difficulty_enabled", True)),
    )
    message = f"Tạo kế hoạch Quiz {total_questions} câu theo các tiêu chí đang bật."
    return {
        "ok": True,
        "planner_engine": "bank_release_constraint_modes_v1",
        "sampling_strategy": "constraint_pool",
        "uses_llm": False,
        "release_id": release.id,
        "release_code": release.release_code,
        "openedx_library_key": release.openedx_library_key,
        "requested_total_questions": total_questions,
        "total_questions": total_questions,
        "target_counts": {key.upper(): value for key, value in requested.items()},
        "effective_target_counts": {key.upper(): value for key, value in effective_diff.items()},
        "matrix_target_counts": {key.upper(): value for key, value in effective_diff.items()},
        "question_type_target_counts": type_targets,
        "coverage": coverage,
        "slots": slots,
        "warnings": warnings,
        "assigned_question_count": len({qid for slot in slots for qid in slot["question_ids"]}),
        "assigned_component_count": len({cid for slot in slots for cid in slot["openedx_problem_ids"]}),
        "source_release_pick_counts": {str(release.id): total_questions},
        "source_release_candidate_counts": source_counts,
        "classification_policy": "constraints_v1",
        "hard_guard": {
            "valid": True,
            "summary": "Chỉ chia theo tiêu chí được bật; nếu cả hai tắt chỉ random đủ N câu.",
        },
        "message": message,
        **_common_plan_meta(entries, config, all_legacy),
        **_ui_notice("success", message),
    }


def _balanced_targets(releases: list[str], capacity: dict[str, int], total: int) -> dict[str, int]:
    if total < len(releases):
        raise ValueError(f"Final test cần ít nhất {len(releases)} câu để mỗi Bài có ít nhất 1 câu.")
    missing = [release_id for release_id in releases if capacity.get(release_id, 0) <= 0]
    if missing:
        raise ValueError("Final test có Bài không có câu hợp lệ: " + ", ".join(missing))

    result = {release_id: 0 for release_id in releases}
    for _ in range(total):
        choices = [release_id for release_id in releases if result[release_id] < capacity.get(release_id, 0)]
        if not choices:
            raise ValueError(f"Không đủ tổng số câu Final test: cần {total}.")
        chosen = min(choices, key=lambda release_id: (result[release_id], releases.index(release_id)))
        result[chosen] += 1
    return result


def _allocate_final(
    releases: list[str],
    release_targets: dict[str, int],
    pair_targets: dict[tuple[str, str], int],
    capacity: dict[tuple[str, tuple[str, str]], int],
) -> dict[tuple[str, tuple[str, str]], int]:
    remaining_release = dict(release_targets)
    used: dict[tuple[str, tuple[str, str]], int] = defaultdict(int)
    pair_order = sorted(
        [pair for pair, count in pair_targets.items() if count > 0],
        key=lambda pair: sum(capacity.get((release_id, pair), 0) for release_id in releases) - pair_targets[pair],
    )
    for pair in pair_order:
        for _ in range(pair_targets[pair]):
            choices = [
                release_id
                for release_id in releases
                if remaining_release[release_id] > 0
                and used[(release_id, pair)] < capacity.get((release_id, pair), 0)
            ]
            if not choices:
                raise ValueError(
                    "Không thể vừa giữ phân bổ theo Bài vừa đáp ứng Độ khó/Định dạng hiện tại. "
                    "Hãy tăng số câu Final hoặc nới một tiêu chí."
                )
            chosen = max(
                choices,
                key=lambda release_id: (
                    remaining_release[release_id],
                    capacity.get((release_id, pair), 0) - used[(release_id, pair)],
                    -releases.index(release_id),
                ),
            )
            used[(chosen, pair)] += 1
            remaining_release[chosen] -= 1

    if any(remaining_release.values()):
        raise ValueError("Final test chưa phân bổ đủ quota cho mọi Bài nguồn.")
    return dict(used)


def build_final_constraint_plan(
    workflow,
    *,
    source_releases: list[QuestionBankRelease],
    source_details: list[dict] | None,
    total_questions: int,
    difficulty_easy: int,
    difficulty_medium: int,
    difficulty_hard: int,
    max_families_per_bank: int = 2,
    config: dict[str, Any],
) -> dict:
    del max_families_per_bank
    if not source_releases:
        raise ValueError("Final test chưa có Release nguồn.")

    entries, source_counts = _prepare_entries(
        workflow,
        source_releases,
        difficulty_enabled=bool(config.get("difficulty_enabled", True)),
        question_type_enabled=bool(config.get("question_type_enabled", False)),
        final_test=True,
    )
    pair_targets, effective_diff, type_targets, warnings, all_legacy = _pair_targets(
        entries,
        total=total_questions,
        easy=difficulty_easy,
        medium=difficulty_medium,
        hard=difficulty_hard,
        config=config,
    )

    release_ids = [str(release.id) for release in source_releases]
    by_release_pair: dict[tuple[str, tuple[str, str]], list[dict]] = defaultdict(list)
    for entry in entries:
        by_release_pair[(entry["release_id"], (entry["difficulty"], entry["question_type"]))].append(entry)
    pair_capacity = {key: len(items) for key, items in by_release_pair.items()}
    eligible_capacity = {
        release_id: sum(
            pair_capacity.get((release_id, pair), 0)
            for pair, count in pair_targets.items()
            if count > 0
        )
        for release_id in release_ids
    }
    release_targets = _balanced_targets(release_ids, eligible_capacity, total_questions)
    allocation = _allocate_final(release_ids, release_targets, pair_targets, pair_capacity)
    release_by_id = {str(release.id): release for release in source_releases}
    detail_by_id = {str(item.get("release_id")): item for item in (source_details or [])}

    slots: list[dict] = []
    coverage: list[dict] = []
    actual = {release_id: 0 for release_id in release_ids}
    for release_id in release_ids:
        release = release_by_id[release_id]
        title = str((detail_by_id.get(release_id) or {}).get("chapter_title") or release.release_code or release_id)
        for pair in pair_targets:
            pick = allocation.get((release_id, pair), 0)
            if pick <= 0:
                continue
            candidates = by_release_pair.get((release_id, pair), [])
            slots.append(_slot(len(slots) + 1, candidates, pick, pair, release, title))
            actual[release_id] += pick
            coverage.append({
                "source_release_id": release_id,
                "source_chapter_title": title,
                "difficulty": "ANY" if pair[0] == "any" else pair[0].upper(),
                "question_type": pair[1],
                "target_questions": pick,
                "candidate_questions": len(candidates),
            })

    if sum(slot["pick_count"] for slot in slots) != total_questions or any(actual[release_id] <= 0 for release_id in release_ids):
        raise ValueError("Final test planner không giữ được đúng tổng số câu và đại diện của mọi Bài.")

    requested = _diff_targets(
        total_questions,
        difficulty_easy,
        difficulty_medium,
        difficulty_hard,
        bool(config.get("difficulty_enabled", True)),
    )
    message = (
        f"Final test lấy đúng {total_questions} câu từ {len(release_ids)} Bài/Release "
        "và cân bằng theo Bài trong giới hạn số câu khả dụng."
    )
    meta = _common_plan_meta(entries, config, all_legacy)
    if not config.get("difficulty_enabled", True):
        meta["difficulty_policy"] = "disabled_random_within_each_lesson"
    if not config.get("question_type_enabled", False):
        meta["question_type_policy"] = "disabled_random_within_each_lesson"

    return {
        "ok": True,
        "planner_engine": "final_test_balanced_release_constraint_modes_v1",
        "uses_llm": False,
        "release_id": release_ids[0],
        "release_code": source_releases[0].release_code,
        "openedx_library_key": source_releases[0].openedx_library_key,
        "source_release_ids": release_ids,
        "source_release_codes": [str(release.release_code or "") for release in source_releases],
        "source_release_count": len(release_ids),
        "source_chapters": list(source_details or []),
        "requested_total_questions": total_questions,
        "total_questions": total_questions,
        "target_counts": {key.upper(): value for key, value in requested.items()},
        "effective_target_counts": {key.upper(): value for key, value in effective_diff.items()},
        "matrix_target_counts": {key.upper(): value for key, value in effective_diff.items()},
        "question_type_target_counts": type_targets,
        "coverage": coverage,
        "slots": slots,
        "warnings": warnings,
        "assigned_question_count": len({qid for slot in slots for qid in slot["question_ids"]}),
        "assigned_component_count": len({cid for slot in slots for cid in slot["openedx_problem_ids"]}),
        "source_release_pick_counts": actual,
        "source_release_candidate_counts": source_counts,
        "source_release_distribution_policy": "balanced_by_lesson_capacity_aware_v1",
        "classification_policy": "constraints_v1",
        "hard_guard": {
            "valid": True,
            "summary": "Final test luôn chia theo từng Bài/Release; hai tiêu chí còn lại bật/tắt độc lập.",
        },
        "message": message,
        **meta,
        **_ui_notice("success", message),
    }
