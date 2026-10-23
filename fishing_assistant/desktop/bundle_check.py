"""EXE 无操作启动自检；不会启动热键、截图、更新或游戏任务。"""
from __future__ import annotations

import json
from pathlib import Path
import sys
import traceback


def verify_bundle(report_path: str) -> int:
    report = {"ok": False}
    window = None
    engine = None
    try:
        import cv2
        from PySide6.QtCore import qVersion
        from PySide6.QtSvg import QSvgRenderer
        from PySide6.QtWidgets import QApplication
        from fishing_assistant.config import AppConfig
        from fishing_assistant.constants import APP_VERSION, resource_path, REMOTE_PREVIEW_ENABLED
        from fishing_assistant.engine import FishingEngine
        from fishing_assistant.inventory_cleanup import InventoryCleanupVision
        from fishing_assistant.features.crafting.recognition import CraftVision
        from fishing_assistant.desktop.main_window import MainWindow
        from fishing_assistant.desktop.design import ui_font

        app = QApplication.instance() or QApplication([sys.argv[0]])
        app.setStyle("Fusion")
        app.setFont(ui_font())
        engine = FishingEngine()
        engine._config = AppConfig(voice_alerts_enabled=False)

        # 自检配置只留在内存；不覆盖用户原有主题、窗口与校准数据。
        def update_config(**changes):
            engine._config = engine._config.copy(**changes)
            return engine.config()

        engine.update_config = update_config
        window = MainWindow(engine)
        for theme in ("day", "night"):
            window._apply_theme(theme)
            for index in range(window.stack.count()):
                window._select_page(index)
                app.processEvents()
            window.crafting_hub.setCurrentIndex(1)
            app.processEvents()
        assert not engine.is_monitoring() and not engine.is_crafting()
        for key, text in (("none", "F8"), ("f10", "F8 / F10"), ("esc", "F8 / Esc")):
            index = window.stop_hotkey_combo.findData(key)
            assert index >= 0, f"stop hotkey choice missing: {key}"
            window.stop_hotkey_combo.setCurrentIndex(index)
            assert engine.config().stop_hotkey == key
            assert window.crafting_page.stop.text() == f"停止（{text}）"
        assert not REMOTE_PREVIEW_ENABLED
        checkmark = resource_path("fishing_assistant", "assets", "checkmark.svg")
        assert QSvgRenderer(str(checkmark)).isValid(), "checkbox SVG unavailable"
        names = ("inventory_items_tab.png", "inventory_tidy_text.png", "cleanup_bold_on.png", "cleanup_bold_off.png")
        for name in names:
            assert InventoryCleanupVision._load_template(resource_path("fishing_assistant", "assets", name)) is not None
        assert InventoryCleanupVision._get_feature_set() is not None
        crafting = CraftVision()
        queue_names = ("queue_ring", "empty", "empty_cloth", "empty_cloth_right",
                       "percent", "percent_100", "percent_100_iron", "percent_100_cloth", "percent_100_silk",
                       "detail_iron", "ingredient_ore", "ingredient_iron_ore")
        for name in queue_names:
            assert crafting._template(name) is not None, f"crafting template unavailable: {name}"
        report.update(ok=True, version=APP_VERSION, qt=qVersion(), opencv=cv2.__version__,
                      pages=window.stack.count(), crafting_tabs=window.crafting_hub.count(),
                      assets=list(names)+[checkmark.name], crafting_queue_assets=list(queue_names),
                      game_input_started=False)
    except Exception:
        report["error"] = traceback.format_exc()
    finally:
        if window is not None:
            window.close()
        elif engine is not None:
            engine.close()
    Path(report_path).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0 if report["ok"] else 1
