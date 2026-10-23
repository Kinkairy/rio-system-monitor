"""Keep the supported Qt entrypoint separate from retired implementations."""
import ast
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class EntrypointTests(unittest.TestCase):
    def test_launcher_uses_qt(self):
        tree = ast.parse((ROOT / 'launch.py').read_text(encoding='utf-8'))
        self.assertTrue(any(
            isinstance(node, ast.ImportFrom)
            and node.module == 'rio_monitor.qt_app'
            and any(alias.name == 'main' for alias in node.names)
            for node in ast.walk(tree)
        ))

    def test_runtime_has_no_retired_ui_dependencies(self):
        forbidden = {'tkinter', 'pystray', 'rio_monitor.app',
                     'rio_monitor.settings_ui', 'rio_monitor.window', 'rio_monitor.gpu'}
        for path in (ROOT / 'src' / 'rio_monitor').rglob('*.py'):
            tree = ast.parse(path.read_text(encoding='utf-8'))
            for node in ast.walk(tree):
                names = []
                if isinstance(node, ast.Import):
                    names = [alias.name for alias in node.names]
                elif isinstance(node, ast.ImportFrom):
                    module = node.module or ''
                    package = list(path.relative_to(ROOT / 'src').parts[:-1])
                    if node.level:
                        package = package[:len(package) - node.level + 1]
                        module = '.'.join(package + ([module] if module else []))
                    names = [module] + [module + '.' + alias.name for alias in node.names]
                for name in names:
                    with self.subTest(path=str(path), module=name):
                        self.assertFalse(any(name == old or name.startswith(old + '.') for old in forbidden))
