"""模块边界与兼容入口回归，不向游戏发送输入。"""
import ast
import importlib
import os
from pathlib import Path
import unittest
from unittest.mock import MagicMock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication, QLabel
from PySide6.QtGui import QPalette

from fishing_assistant.config import AppConfig
from fishing_assistant.engine import FishingEngine
from fishing_assistant.features.fishing_history.store import FishingHistorySummary
from fishing_assistant.ui import MainWindow


PACKAGE = Path(__file__).resolve().parents[1] / "fishing_assistant"


class ArchitectureTests(unittest.TestCase):
    def test_legacy_imports_reference_the_same_classes(self):
        pairs = (
            ("ui", "desktop.main_window", "MainWindow"),
            ("ui", "desktop.widgets", "Card"),
            ("ui", "desktop.widgets", "ScrollSafeComboBox"),
            ("ui", "desktop.dialogs", "InventoryCleanupWarningDialog"),
            ("ui", "desktop.floating_status", "FloatingStatusBar"),
            ("engine", "automation.models", "EngineEvent"),
            ("engine", "automation.models", "IconState"),
            ("engine", "automation.models", "StaminaBarSample"),
            ("crafting", "features.crafting.model", "CraftSession"),
            ("crafting_runtime", "features.crafting.runner", "run_crafting"),
            ("crafting_vision", "features.crafting.recognition", "CraftVision"),
            ("crafting_ui", "features.crafting.page", "CraftingPage"),
        )
        for legacy, current, name in pairs:
            with self.subTest(name=name):
                self.assertIs(getattr(importlib.import_module("fishing_assistant."+legacy), name),
                              getattr(importlib.import_module("fishing_assistant."+current), name))

    def test_internal_mixins_have_no_constructor_or_method_collisions(self):
        for owner in (FishingEngine, MainWindow):
            methods = {}
            for base in owner.__mro__:
                if not base.__module__.startswith("fishing_assistant."):
                    continue
                if base is not owner:
                    self.assertNotIn("__init__", base.__dict__, base.__name__)
                for name, value in base.__dict__.items():
                    if isinstance(value, (classmethod, staticmethod)) or callable(value):
                        self.assertNotIn(name, methods, f"{owner.__name__}.{name}: {base.__name__} overrides {methods.get(name)}")
                        methods[name] = base.__name__

    def test_execution_and_recognition_do_not_import_desktop(self):
        for folder in ("automation", "vision"):
            for path in (PACKAGE / folder).rglob("*.py"):
                for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
                    if isinstance(node, ast.ImportFrom):
                        module = node.module or ""
                        self.assertFalse(module.startswith(("fishing_assistant.desktop", "fishing_assistant.ui", "PySide6")), str(path))

    def test_implementation_does_not_import_compatibility_ui(self):
        for folder in ("desktop", "automation", "features"):
            for path in (PACKAGE / folder).rglob("*.py"):
                for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
                    if isinstance(node, ast.ImportFrom):
                        self.assertNotEqual(node.module, "fishing_assistant.ui", str(path))

    def test_new_packages_have_explicit_package_markers(self):
        for path in (
            "automation",
            "desktop",
            "desktop/pages",
            "desktop/controllers",
            "features",
            "features/crafting",
            "features/fishing_history",
        ):
            self.assertTrue((PACKAGE / path / "__init__.py").is_file(), path)

    def test_crafting_model_stays_independent_of_ui_and_input(self):
        source = (PACKAGE / "features/crafting/model.py").read_text(encoding="utf-8")
        for node in ast.walk(ast.parse(source)):
            if isinstance(node, ast.ImportFrom):
                self.assertIn(node.module, {"__future__", "dataclasses"})
            self.assertNotIsInstance(node, ast.Import)


class AllPagesSmokeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_all_pages_themes_and_shutdown_with_mock_engine(self):
        engine = MagicMock()
        config = [AppConfig(voice_alerts_enabled=False)]
        engine.config.side_effect = lambda: config[0].copy()
        def update(**changes):
            config[0] = config[0].copy(**changes)
            return config[0].copy()
        engine.update_config.side_effect = update
        engine.is_monitoring.return_value = False
        engine.is_crafting.return_value = False
        engine.fishing_history_summary.return_value = FishingHistorySummary(0, 0, 0, 0, 0)
        engine.fishing_history_sessions.return_value = []
        with patch("fishing_assistant.window_target.list_target_windows", return_value=[]):
            window = MainWindow(engine)
        try:
            self.assertEqual(window.stack.count(), len(MainWindow.PAGE_META))
            for theme in ("day", "night"):
                window._apply_theme(theme)
                bar = window.floating_status_bar
                bar.set_calibrated(True)
                bar.set_runtime("等待上钩", "running")
                self.app.processEvents()
                title = bar.findChild(QLabel, "floatingTitle")
                self.assertEqual(title.palette().color(QPalette.ColorRole.WindowText).name(),
                                 "#172b45" if theme == "day" else "#f4f9ff")
                self.assertEqual(bar.runtime_label.palette().color(QPalette.ColorRole.WindowText).name(),
                                 "#187352" if theme == "day" else "#80e7bf")
                for index in range(window.stack.count()):
                    window._select_page(index)
                    self.app.processEvents()
                    self.assertEqual(window.stack.currentIndex(), index)
                    self.assertIsNotNone(window.stack.currentWidget())
            self.assertFalse(hasattr(window, "remote_panel"))
            engine.start.assert_not_called()
            engine.start_crafting.assert_not_called()
            engine.set_event_callback.assert_called_once()
        finally:
            window.close()
            window.deleteLater()
            self.app.processEvents()
        engine.close.assert_called_once()


if __name__ == "__main__":
    unittest.main()
