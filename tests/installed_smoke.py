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
print('Installed wheel smoke tests passed')
