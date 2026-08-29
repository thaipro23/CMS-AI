#!/usr/bin/env python3
"""Static packaging gate for exception/error boundaries.

This intentionally does not outlaw every ``except Exception``. A large mature
service legitimately has best-effort audit/cleanup paths. The gate blocks
patterns that can make production state lie to operators or leak internals:

* bare ``except:``;
* Celery tasks that swallow a broad failure and return SUCCESS;
* broad API catches that expose ``str(exc)`` directly without the centralized
  public error mapper;
* broad catches whose entire body is ``pass`` are reported as warnings so they
  remain visible in the release report instead of being silently normalized.
"""
from __future__ import annotations

import argparse
import ast
from dataclasses import dataclass
from pathlib import Path


BROAD_NAMES = {'Exception', 'BaseException'}


@dataclass(frozen=True)
class Finding:
    severity: str
    path: str
    line: int
    code: str
    message: str


def _is_broad(handler: ast.ExceptHandler) -> bool:
    if handler.type is None:
        return True
    if isinstance(handler.type, ast.Name):
        return handler.type.id in BROAD_NAMES
    if isinstance(handler.type, ast.Tuple):
        return any(isinstance(item, ast.Name) and item.id in BROAD_NAMES for item in handler.type.elts)
    return False


def _decorator_text(node: ast.AST) -> str:
    try:
        return ast.unparse(node)
    except Exception:
        return ''


def _is_celery_task(fn: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    text = ' '.join(_decorator_text(item) for item in fn.decorator_list)
    return '.task' in text or 'shared_task' in text


def _contains_raise(nodes: list[ast.stmt]) -> bool:
    return any(isinstance(item, ast.Raise) for node in nodes for item in ast.walk(node))


def _contains_return(nodes: list[ast.stmt]) -> bool:
    return any(isinstance(item, ast.Return) for node in nodes for item in ast.walk(node))


def _only_pass(nodes: list[ast.stmt]) -> bool:
    useful = []
    for node in nodes:
        if isinstance(node, ast.Pass):
            continue
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant):
            continue
        useful.append(node)
    return not useful


def _call_is_public_mapper(call: ast.Call) -> bool:
    func = call.func
    if isinstance(func, ast.Name):
        return func.id == 'public_http_exception'
    if isinstance(func, ast.Attribute):
        return func.attr == 'public_http_exception'
    return False


def _contains_raw_exception_public_message(nodes: list[ast.stmt], exc_name: str | None) -> bool:
    if not exc_name:
        return False
    for node in nodes:
        for item in ast.walk(node):
            if not isinstance(item, ast.Call):
                continue
            # str(exc) is acceptable when it is passed to the centralized mapper;
            # that mapper only exposes ValueError and sanitizes unexpected errors.
            if _call_is_public_mapper(item):
                continue
            for arg in [*item.args, *(kw.value for kw in item.keywords)]:
                if isinstance(arg, ast.Call) and isinstance(arg.func, ast.Name) and arg.func.id == 'str':
                    if arg.args and isinstance(arg.args[0], ast.Name) and arg.args[0].id == exc_name:
                        return True
    return False


def _scan_file(root: Path, path: Path) -> list[Finding]:
    rel = path.relative_to(root).as_posix()
    if '/tests/' in f'/{rel}/':
        return []
    try:
        source = path.read_text(encoding='utf-8')
        tree = ast.parse(source, filename=rel)
    except (OSError, UnicodeDecodeError, SyntaxError) as exc:
        return [Finding('BLOCKER', rel, getattr(exc, 'lineno', 1) or 1, 'PYTHON_PARSE_ERROR', str(exc))]

    findings: list[Finding] = []
    parent: dict[ast.AST, ast.AST] = {}
    for node in ast.walk(tree):
        for child in ast.iter_child_nodes(node):
            parent[child] = node

    task_functions = {
        node for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and _is_celery_task(node)
    }

    for handler in (node for node in ast.walk(tree) if isinstance(node, ast.ExceptHandler)):
        if handler.type is None:
            findings.append(Finding('BLOCKER', rel, handler.lineno, 'BARE_EXCEPT', 'Bare except is forbidden; catch an explicit exception type.'))
        if not _is_broad(handler):
            continue

        ancestor = parent.get(handler)
        owner: ast.FunctionDef | ast.AsyncFunctionDef | None = None
        while ancestor is not None:
            if isinstance(ancestor, (ast.FunctionDef, ast.AsyncFunctionDef)):
                owner = ancestor
                break
            ancestor = parent.get(ancestor)

        if owner in task_functions and _contains_return(handler.body) and not _contains_raise(handler.body):
            findings.append(Finding(
                'BLOCKER', rel, handler.lineno, 'CELERY_SWALLOWED_FAILURE',
                f'Celery task {owner.name} returns from a broad exception handler without re-raising; Celery would report SUCCESS.',
            ))

        exc_name = handler.name if isinstance(handler.name, str) else None
        if rel.startswith('backend/app/api/routes/') and _contains_raw_exception_public_message(handler.body, exc_name):
            findings.append(Finding(
                'BLOCKER', rel, handler.lineno, 'RAW_EXCEPTION_PUBLIC_MESSAGE',
                'Broad API exception is converted to public text outside public_http_exception().',
            ))

        if _only_pass(handler.body):
            findings.append(Finding(
                'WARNING', rel, handler.lineno, 'BROAD_PASS',
                f'Broad exception is intentionally ignored in {owner.name if owner else "module scope"}; verify this remains best-effort cleanup/audit.',
            ))
    return findings


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', default='.', help='Project root')
    parser.add_argument('--report', default='', help='Optional markdown report path')
    args = parser.parse_args()
    root = Path(args.root).resolve()
    findings: list[Finding] = []
    for path in sorted((root / 'backend/app').rglob('*.py')):
        findings.extend(_scan_file(root, path))

    blockers = [item for item in findings if item.severity == 'BLOCKER']
    warnings = [item for item in findings if item.severity == 'WARNING']
    print(f'error-boundary-contract: blockers={len(blockers)} warnings={len(warnings)}')
    for item in findings:
        print(f'{item.severity}: {item.path}:{item.line} [{item.code}] {item.message}')

    if args.report:
        report_path = Path(args.report)
        report_path.parent.mkdir(parents=True, exist_ok=True)
        with report_path.open('w', encoding='utf-8') as fh:
            fh.write('# Error Boundary Contract Report\n\n')
            fh.write(f'- Blockers: **{len(blockers)}**\n- Warnings: **{len(warnings)}**\n\n')
            fh.write('| Severity | Code | Location | Finding |\n|---|---|---|---|\n')
            for item in findings:
                message = item.message.replace('|', '\\|')
                fh.write(f'| {item.severity} | `{item.code}` | `{item.path}:{item.line}` | {message} |\n')
            if not findings:
                fh.write('| PASS | `NONE` | — | No findings. |\n')
    return 1 if blockers else 0


if __name__ == '__main__':
    raise SystemExit(main())
