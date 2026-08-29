from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from app.services.question_content import normalize_question_type

AI_GENERATABLE_TYPES = ('single_select', 'multi_select')
QUIZ_SUPPORTED_TYPES = ('single_select', 'multi_select', 'text_input', 'numerical_input')


def proportional_counts(*, total: int, weights: Mapping[str, int | float], allowed_types: Sequence[str], default_type: str = 'single_select') -> dict[str, int]:
    total = int(total or 0)
    if total < 0:
        raise ValueError('Tổng số câu hỏi không được âm.')
    allowed = tuple(normalize_question_type(item) for item in allowed_types)
    if not allowed:
        raise ValueError('Không có loại câu hỏi nào được phép.')
    normalized: dict[str, float] = {item: 0.0 for item in allowed}
    for raw_type, raw_weight in (weights or {}).items():
        qtype = normalize_question_type(raw_type)
        if qtype not in normalized:
            raise ValueError(f'Loại câu hỏi {qtype} không được phép trong thao tác này.')
        try:
            weight = float(raw_weight or 0)
        except (TypeError, ValueError) as exc:
            raise ValueError(f'Tỷ lệ loại câu hỏi {qtype} không hợp lệ.') from exc
        if weight < 0:
            raise ValueError(f'Tỷ lệ loại câu hỏi {qtype} không được âm.')
        normalized[qtype] = weight
    weight_sum = sum(normalized.values())
    if weight_sum <= 0:
        fallback = normalize_question_type(default_type)
        if fallback not in normalized:
            raise ValueError('Loại câu hỏi mặc định không nằm trong tập loại được phép.')
        normalized[fallback] = 1.0
        weight_sum = 1.0
    if total == 0:
        return {item: 0 for item in allowed}
    raw_counts = {item: total * normalized[item] / weight_sum for item in allowed}
    counts = {item: int(raw_counts[item]) for item in allowed}
    remainder = total - sum(counts.values())
    order_index = {item: index for index, item in enumerate(allowed)}
    order = sorted(allowed, key=lambda item: (raw_counts[item] - counts[item], -order_index[item]), reverse=True)
    for item in order[:remainder]:
        counts[item] += 1
    if sum(counts.values()) != total:
        raise ValueError('Lỗi nội bộ khi phân bổ tỷ lệ loại câu hỏi.')
    return counts


def exact_type_counts(*, total: int, single_select_count: int | None = None, multi_select_count: int | None = None, text_input_count: int | None = None, numerical_input_count: int | None = None, legacy_default_single: bool = True) -> dict[str, int]:
    total = int(total or 0)
    if total < 1:
        raise ValueError('Tổng số câu Quiz phải lớn hơn 0.')
    raw = {
        'single_select': single_select_count,
        'multi_select': multi_select_count,
        'text_input': text_input_count,
        'numerical_input': numerical_input_count,
    }
    if all(value is None for value in raw.values()):
        return {'single_select': total if legacy_default_single else 0, 'multi_select': 0, 'text_input': 0, 'numerical_input': 0}
    counts: dict[str, int] = {}
    for qtype, value in raw.items():
        value = 0 if value is None else value
        try:
            count = int(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f'Quota {qtype} không hợp lệ.') from exc
        if count < 0:
            raise ValueError(f'Quota {qtype} không được âm.')
        if count > total:
            raise ValueError(f'Quota {qtype} không được lớn hơn tổng số câu Quiz.')
        counts[qtype] = count
    if sum(counts.values()) != total:
        raise ValueError(f'Tổng quota theo loại câu hỏi phải bằng tổng số câu Quiz ({sum(counts.values())}/{total}).')
    return counts


def allocate_column_counts_to_rows(row_counts: Sequence[int], column_counts: Mapping[str, int]) -> list[dict[str, int]]:
    rows = [int(value or 0) for value in row_counts]
    if any(value < 0 for value in rows):
        raise ValueError('Số câu của generation bucket không được âm.')
    columns = {normalize_question_type(key): int(value or 0) for key, value in column_counts.items()}
    if any(value < 0 for value in columns.values()):
        raise ValueError('Quota loại câu hỏi không được âm.')
    if sum(rows) != sum(columns.values()):
        raise ValueError(f'Không thể phân bổ loại câu hỏi: bucket={sum(rows)}, quota={sum(columns.values())}.')
    if not rows:
        return []
    remaining = dict(columns)
    result: list[dict[str, int]] = []
    remaining_rows_total = sum(rows)
    keys = tuple(columns)
    for index, row_total in enumerate(rows):
        if index == len(rows) - 1:
            allocation = dict(remaining)
        elif row_total == 0:
            allocation = {key: 0 for key in keys}
        else:
            allocation = proportional_counts(total=row_total, weights=remaining, allowed_types=keys, default_type=keys[0])
            # Rebalance any largest-remainder overflow against exhausted columns.
            for key in keys:
                overflow = max(0, allocation[key] - remaining[key])
                if not overflow:
                    continue
                allocation[key] -= overflow
                for candidate in sorted((item for item in keys if item != key), key=lambda item: (remaining[item] - allocation[item], item), reverse=True):
                    capacity = max(0, remaining[candidate] - allocation[candidate])
                    take = min(capacity, overflow)
                    allocation[candidate] += take
                    overflow -= take
                    if not overflow:
                        break
                if overflow:
                    raise ValueError('Không thể cân bằng quota loại câu hỏi giữa các generation bucket.')
        if sum(allocation.values()) != row_total:
            raise ValueError('Lỗi nội bộ khi phân bổ quota loại câu hỏi theo generation bucket.')
        result.append(allocation)
        for key, value in allocation.items():
            remaining[key] -= value
            if remaining[key] < 0:
                raise ValueError('Lỗi nội bộ: quota loại câu hỏi bị phân bổ âm.')
        remaining_rows_total -= row_total
    if remaining_rows_total != 0 or any(remaining.values()):
        raise ValueError('Lỗi nội bộ: quota loại câu hỏi chưa được phân bổ hết.')
    return result


def feasible_type_difficulty_matrix(*, difficulty_targets: Mapping[str, int], type_targets: Mapping[str, int], availability: Mapping[tuple[str, str], int]) -> dict[tuple[str, str], int]:
    difficulties = tuple(str(key) for key in difficulty_targets)
    normalized_type_targets: dict[str, int] = {}
    for key, value in type_targets.items():
        qtype = normalize_question_type(key)
        if qtype in normalized_type_targets:
            raise ValueError(f'Quota loại câu hỏi bị trùng sau chuẩn hóa: {qtype}.')
        normalized_type_targets[qtype] = int(value or 0)
    qtypes = tuple(normalized_type_targets)
    row_total = sum(int(difficulty_targets[key] or 0) for key in difficulties)
    col_total = sum(normalized_type_targets.values())
    if row_total != col_total:
        raise ValueError(f'Quota difficulty ({row_total}) và loại câu hỏi ({col_total}) không cùng tổng.')
    if any(int(value or 0) < 0 for value in difficulty_targets.values()) or any(value < 0 for value in normalized_type_targets.values()):
        raise ValueError('Quota Quiz không được âm.')

    source, sink = '__source__', '__sink__'
    graph: dict[str, dict[str, int]] = {}
    def add_edge(left: str, right: str, capacity: int) -> None:
        graph.setdefault(left, {})[right] = max(0, int(capacity or 0))
        graph.setdefault(right, {}).setdefault(left, 0)
    for diff in difficulties:
        add_edge(source, f'd:{diff}', int(difficulty_targets[diff] or 0))
    for diff in difficulties:
        for qtype in qtypes:
            add_edge(f'd:{diff}', f't:{qtype}', int(availability.get((diff, qtype), 0) or 0))
    for qtype in qtypes:
        add_edge(f't:{qtype}', sink, normalized_type_targets[qtype])

    residual = {node: dict(edges) for node, edges in graph.items()}
    flow = 0
    while True:
        parent: dict[str, str | None] = {source: None}
        queue = [source]
        for node in queue:
            for nxt in sorted(residual.get(node, {})):
                if nxt in parent or residual[node][nxt] <= 0:
                    continue
                parent[nxt] = node
                queue.append(nxt)
                if nxt == sink:
                    break
            if sink in parent:
                break
        if sink not in parent:
            break
        path_capacity = 10**9
        node = sink
        while parent[node] is not None:
            prev = parent[node]
            path_capacity = min(path_capacity, residual[prev][node])
            node = prev
        node = sink
        while parent[node] is not None:
            prev = parent[node]
            residual[prev][node] -= path_capacity
            residual[node][prev] = residual[node].get(prev, 0) + path_capacity
            node = prev
        flow += path_capacity
    if flow != row_total:
        available_by_diff = {diff: sum(int(availability.get((diff, qtype), 0) or 0) for qtype in qtypes) for diff in difficulties}
        available_by_type = {qtype: sum(int(availability.get((diff, qtype), 0) or 0) for diff in difficulties) for qtype in qtypes}
        raise ValueError(
            'Release không đủ tổ hợp difficulty × loại câu hỏi để đáp ứng quota chính xác. '
            f'Cần difficulty={dict(difficulty_targets)}, type={normalized_type_targets}; '
            f'hiện có difficulty={available_by_diff}, type={available_by_type}.'
        )
    matrix: dict[tuple[str, str], int] = {}
    for diff in difficulties:
        for qtype in qtypes:
            capacity = int(availability.get((diff, qtype), 0) or 0)
            remaining_capacity = residual.get(f'd:{diff}', {}).get(f't:{qtype}', 0)
            matrix[(diff, qtype)] = capacity - remaining_capacity
    if any(value < 0 for value in matrix.values()):
        raise ValueError('Lỗi nội bộ khi giải quota Quiz theo loại câu hỏi.')
    return matrix


def type_counts_from_payload(payload: Mapping[str, Any], *, total: int) -> dict[str, int]:
    return exact_type_counts(total=total, single_select_count=payload.get('single_select_count'), multi_select_count=payload.get('multi_select_count'), text_input_count=payload.get('text_input_count'), numerical_input_count=payload.get('numerical_input_count'))
