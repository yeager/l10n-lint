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
print('Installed wheel smoke tests passed')
