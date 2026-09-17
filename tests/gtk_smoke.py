import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import l10n_lint_gtk as gui
from unittest.mock import patch
from gi.repository import Gio, GLib
gui.load_settings = lambda: {'enabled_rules': list(gui.RULES), 'recursive': True}
gui.L10nLintWindow._load_history = lambda self: None
app = gui.L10nLintApp()
app.set_flags(Gio.ApplicationFlags.HANDLES_OPEN | Gio.ApplicationFlags.NON_UNIQUE)
assert app.register(None)
app.activate()
window = app.props.active_window
assert window is not None
prefs = gui.PreferencesWindow(app)
assert len(prefs.rule_switches) == len(gui.RULES)
with patch.object(gui, 'load_settings', return_value={'enabled_rules': ['placeholder-mismatch']}):
    window.settings = gui.load_settings()
    with patch('l10n_lint.fetch_url_file', return_value=('sv.po', 'msgid "Hello %s"\nmsgstr "Hej"\n')):
        window._run_lint('https://example.org/sv.po')
    context = GLib.MainContext.default()
    for _ in range(100):
        if not context.pending(): break
        context.iteration(False)
    assert window.current_result.files_checked == 1
    assert window.current_result.error_count == 1
prefs.close()
window.close()
app.quit()
print('GTK window, preferences and URL result display passed')
