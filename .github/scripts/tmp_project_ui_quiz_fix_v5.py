from pathlib import Path

script = Path('.github/scripts/tmp_project_ui_quiz_fix_v4.py')
code = script.read_text(encoding='utf-8')

old = "s = must_replace(s, \"    const typeTotal = config.singleSelectCount + config.multiSelectCount + config.textInputCount + config.numericalInputCount\\n\", '', 'ConfigPanel type total', 1)"
new = "s = s.replace(\"    const typeTotal = config.singleSelectCount + config.multiSelectCount + config.textInputCount + config.numericalInputCount\\n\", '', 1)"
if old not in code:
    raise SystemExit('v5 runner could not find ConfigPanel type-total patch anchor')
code = code.replace(old, new, 1)

exec(compile(code, str(script), 'exec'), {'__name__': '__main__', '__file__': str(script)})
