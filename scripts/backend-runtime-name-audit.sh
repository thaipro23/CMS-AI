#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT_DIR="${1:-$ROOT/.runtime/backend-runtime-name-audit}"
mkdir -p "$OUT_DIR"
python - "$ROOT" "$OUT_DIR" <<'PY'
import builtins, json, symtable, sys
from pathlib import Path
root=Path(sys.argv[1]); out=Path(sys.argv[2]); source_root=root/'backend'/'app'
known=set(dir(builtins))|{'__name__','__file__','__package__','__spec__','__loader__','__cached__','__builtins__','TYPE_CHECKING'}
findings=[]; syntax_errors=[]; scanned=0
for path in sorted(source_root.rglob('*.py')):
    if '__pycache__' in path.parts: continue
    scanned+=1; source=path.read_text(encoding='utf-8')
    try: table=symtable.symtable(source,str(path),'exec')
    except SyntaxError as exc:
        syntax_errors.append({'path':path.relative_to(root).as_posix(),'line':exc.lineno,'message':exc.msg}); continue
    module_names=set(known)
    for symbol in table.get_symbols():
        if symbol.is_assigned() or symbol.is_imported() or symbol.is_namespace() or symbol.is_parameter(): module_names.add(symbol.get_name())
    def visit(scope):
        for symbol in scope.get_symbols():
            if symbol.is_referenced() and symbol.is_global() and symbol.get_name() not in module_names:
                findings.append({'path':path.relative_to(root).as_posix(),'scope':scope.get_name(),'name':symbol.get_name()})
        for child in scope.get_children(): visit(child)
    visit(table)
quiz=(source_root/'services/question_bank/quiz_creation.py').read_text(encoding='utf-8')
critical={
 'quiz_imports_department':'    Department,' in quiz,
 'quiz_imports_sequence_matcher':'from difflib import SequenceMatcher' in quiz,
 'quiz_imports_normalize_difficulty':'from app.services.question_family import normalize_difficulty' in quiz,
 'quiz_uses_department':'self.db.get(Department, subject.department_id)' in quiz,
 'quiz_uses_sequence_matcher':'SequenceMatcher(None, bank_key, section_key).ratio()' in quiz,
 'quiz_uses_normalize_difficulty':'normalize_difficulty(row.difficulty or question.difficulty)' in quiz,
}
status='READY' if not findings and not syntax_errors and all(critical.values()) else 'BLOCKED'
payload={'status':status,'files_scanned':scanned,'undefined_global_count':len(findings),'syntax_error_count':len(syntax_errors),'critical_checks':critical,'undefined_globals':findings,'syntax_errors':syntax_errors,'note':'Static symbol-table audit for missing module imports/global names. Runtime integration tests remain required for external services and database branches.'}
(out/'backend-runtime-name-audit.json').write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(payload,ensure_ascii=False,indent=2))
if status!='READY': raise SystemExit(1)
PY
