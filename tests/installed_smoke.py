"""Run with the clean wheel environment's Python, outside the source tree."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import l10n_lint
import l10n_project

# Explicitly ensure imports came from the installed environment.
assert 'site-packages' in str(Path(l10n_lint.__file__))
assert 'site-packages' in str(Path(l10n_project.__file__))
command = Path(sys.executable).parent / 'l10n-lint'
with tempfile.TemporaryDirectory() as directory:
    root = Path(directory)
    file = root / 'sv.po'
    file.write_text('msgid "Hello %s"\nmsgstr "Hej"\n', encoding='utf-8')
    run = subprocess.run([str(command), '-f', 'sarif', str(file)], cwd=root, text=True, capture_output=True)
    assert run.returncode == 2, run.stderr
    findings = json.loads(run.stdout)['runs'][0]['results']
    assert any(i['ruleId'] == 'placeholder-mismatch' for i in findings)
    assert subprocess.run([str(command), '--check', str(root / 'missing.po')], cwd=root).returncode == 2
    for source, translation, context, expected in [
        ('Date: yyyy-mm-dd', 'Datum: yyyy-mm-dd', '', 0),
        ('View', 'Vy', 'Color Management', 0),
        ('View', 'Vy', 'menu', 2),
        ('sweep-line solver', 'sveplinjelösaren', '', 0),
        ('Command-line options', 'Alternativ för kommandolinjen', '', 2),
        ('Date: yyyy-mm-dd', 'Kommmando yyyy-mm-dd', '', 2),
    ]:
        file.write_text(
            ('msgctxt ' + json.dumps(context) + '\n' if context else '')
            + 'msgid ' + json.dumps(source) + '\nmsgstr '
            + json.dumps(translation, ensure_ascii=False) + '\n', encoding='utf-8')
        run = subprocess.run([str(command), '--checks', 'typo,terminology', '--strict', '--check', str(file)],
                             cwd=root, capture_output=True, text=True)
        assert run.returncode == expected, (source, run.stdout, run.stderr)
    ts = root / 'FreeCAD_sv.ts'
    for content, expected in [
        ('<TS language="sv"><context><name>FreeCAD</name><message>'
         '<source></source><translation></translation></message></context></TS>', 0),
        ('<TS language="sv"><context><name>Property</name><message>'
         '<source>File</source><translation>Fil</translation></message></context></TS>', 0),
        ('<TS language="sv"><context><name>Main Menu</name><message>'
         '<source>File</source><translation>Fil</translation></message></context></TS>', 2),
    ]:
        ts.write_text(content, encoding='utf-8')
        run = subprocess.run([str(command), '--checks', 'terminology', '--strict', '--check', str(ts)],
                             cwd=root, capture_output=True, text=True)
        assert run.returncode == expected, (content, run.stdout, run.stderr)
    xlf = root / 'sv.xlf'
    xlf.write_text(
        '<xliff version="1.2"><file target-language="sv"><body><trans-unit id="save">'
        '<source>Save %s</source><target>Spara %s</target></trans-unit></body></file></xliff>',
        encoding='utf-8')
    run = subprocess.run([str(command), '--strict', '--check', str(xlf)], cwd=root, capture_output=True, text=True)
    assert run.returncode == 0, (run.stdout, run.stderr)
    json_catalog = root / 'sv.json'
    json_catalog.write_text(json.dumps({'@locale': 'sv', 'source': 'Save %s', 'target': 'Spara %d'}), encoding='utf-8')
    run = subprocess.run([str(command), '--strict', '--check', str(json_catalog)], cwd=root, capture_output=True, text=True)
    assert run.returncode == 2, (run.stdout, run.stderr)
print('Installed wheel smoke tests passed')
