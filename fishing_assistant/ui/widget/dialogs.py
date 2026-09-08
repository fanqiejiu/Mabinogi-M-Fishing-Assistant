"""不依赖主窗口状态的确认和更新对话框。"""

from __future__ import annotations

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from ...constants import APP_VERSION
from ...updates import UpdateResult


class UpdateAvailableDialog(QDialog):
    """不遮挡主界面的紧凑更新提醒。"""

    def __init__(self, result: UpdateResult, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._release_url = result.release_url
        self.setObjectName("updateDialog")
        self.setWindowTitle("发现新版本")
        self.setModal(False)
        self.setMinimumWidth(380)
        self.setMaximumWidth(430)
        self.setMaximumHeight(520)
        self.setSizeGripEnabled(False)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 20, 22, 18)
        layout.setSpacing(10)

        title = QLabel("发现新版本")
        title.setObjectName("updateDialogTitle")
        layout.addWidget(title)
        latest = result.latest_version or "新版本"
        version = QLabel(f"当前 v{APP_VERSION}  →  {latest}")
        version.setObjectName("updateDialogVersion")
        layout.addWidget(version)
        message = QLabel("新版本已经发布，可以前往 GitHub 查看更新内容并下载。")
        message.setObjectName("cardHint")
        message.setWordWrap(True)
        layout.addWidget(message)

        notes_title = QLabel("Release 更新说明")
        notes_title.setObjectName("formLabel")
        layout.addWidget(notes_title)
        self.release_notes = QTextBrowser()
        self.release_notes.setObjectName("releaseNotes")
        self.release_notes.setOpenExternalLinks(True)
        self.release_notes.setMinimumHeight(105)
        self.release_notes.setMaximumHeight(180)
        self.release_notes.setMarkdown(result.release_notes or "本次 Release 未填写更新说明。")
        layout.addWidget(self.release_notes)

        actions = QHBoxLayout()
        actions.addStretch(1)
        later_button = QPushButton("关闭")
        later_button.clicked.connect(self.close)
        actions.addWidget(later_button)
        release_button = QPushButton("前往更新")
        release_button.setObjectName("primaryButton")
        release_button.setEnabled(bool(self._release_url))
        release_button.clicked.connect(self._open_release)
        actions.addWidget(release_button)
        layout.addLayout(actions)

    def _open_release(self) -> None:
        if self._release_url:
            QDesktopServices.openUrl(QUrl(self._release_url))
        self.close()


class WOnlyModeWarningDialog(QDialog):
    """切换仅 W 恢复前，要求用户确认镜头和角色朝向。"""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("updateDialog")
        self.setWindowTitle("仅 W 模式使用提醒")
        self.setModal(True)
        self.setMinimumWidth(410)
        self.setMaximumWidth(460)
        self.setSizeGripEnabled(False)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 20, 22, 18)
        layout.setSpacing(11)
        title = QLabel("启用仅按 W 向前恢复前")
        title.setObjectName("updateDialogTitle")
        layout.addWidget(title)
        message = QLabel(
            "请先在游戏设置中将镜头模式改为“手动镜头”，再把镜头视角调整为朝向河岸，"
            "并确认当前为角色背部视角。方向不正确时，持续按 W 可能让角色远离钓鱼区域。"
        )
        message.setObjectName("cardHint")
        message.setWordWrap(True)
        layout.addWidget(message)
        recommendation = QLabel("W → S 往返恢复是默认推荐模式。")
        recommendation.setObjectName("helper")
        recommendation.setWordWrap(True)
        layout.addWidget(recommendation)
        self.acknowledge_check = QCheckBox("我已改为手动镜头，并确认镜头与角色朝向正确")
        layout.addWidget(self.acknowledge_check)
        actions = QHBoxLayout()
        actions.addStretch(1)
        cancel_button = QPushButton("返回 W → S")
        cancel_button.clicked.connect(self.reject)
        actions.addWidget(cancel_button)
        self.confirm_button = QPushButton("继续使用仅 W")
        self.confirm_button.setObjectName("primaryButton")
        self.confirm_button.setEnabled(False)
        self.confirm_button.clicked.connect(self.accept)
        actions.addWidget(self.confirm_button)
        layout.addLayout(actions)
        self.acknowledge_check.toggled.connect(self.confirm_button.setEnabled)


class InventoryCleanupWarningDialog(QDialog):
    """启用自动整理前，明确提示装备会被永久分解。"""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("updateDialog")
        self.setWindowTitle("自动清理背包提醒")
        self.setModal(True)
        self.setMinimumWidth(420)
        self.setMaximumWidth(480)
        self.setSizeGripEnabled(False)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 20, 22, 18)
        layout.setSpacing(11)
        title = QLabel("启用前请确认")
        title.setObjectName("updateDialogTitle")
        layout.addWidget(title)
        message = QLabel(
            "背包满时，助手会进入简单整理，并尝试选择装备、材料、黄金及杂物、"
            "恢复道具四类；整理结果无法由助手撤销。"
        )
        message.setObjectName("cardHint")
        message.setWordWrap(True)
        layout.addWidget(message)
        safety = QLabel(
            "流程会尝试关闭“大胆整理”，并在点击整理前分两轮、每轮连续 3 帧核验。"
            "但这是实验性功能：游戏界面变化或识别误判仍可能导致误操作，"
            "包括意外保留或误用“大胆整理”。"
        )
        safety.setObjectName("helper")
        safety.setWordWrap(True)
        layout.addWidget(safety)
        self.acknowledge_check = QCheckBox("我已知晓上述风险，包括可能误用“大胆整理”")
        layout.addWidget(self.acknowledge_check)
        actions = QHBoxLayout()
        actions.addStretch(1)
        cancel_button = QPushButton("保持关闭")
        cancel_button.clicked.connect(self.reject)
        actions.addWidget(cancel_button)
        self.confirm_button = QPushButton("确认启用")
        self.confirm_button.setObjectName("dangerButton")
        self.confirm_button.setEnabled(False)
        self.confirm_button.clicked.connect(self.accept)
        actions.addWidget(self.confirm_button)
        layout.addLayout(actions)
        self.acknowledge_check.toggled.connect(self.confirm_button.setEnabled)


class InventoryCleanupTestDialog(QDialog):
    """调试页执行真实清理前的二次确认。"""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("updateDialog")
        self.setWindowTitle("测试背包清理流程")
        self.setModal(True)
        self.setMinimumWidth(420)
        self.setMaximumWidth(480)
        self.setSizeGripEnabled(False)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 20, 22, 18)
        layout.setSpacing(11)
        title = QLabel("这不是模拟测试")
        title.setObjectName("updateDialogTitle")
        layout.addWidget(title)
        message = QLabel(
            "此调试不需要启用正式自动清理，也不会修改正式功能开关。"
            "点击继续后会立刻打开游戏背包并真实执行整理，物品可能被永久分解或出售。"
            "请先暂停普通监测，并让游戏停留在可正常打开背包的画面。"
        )
        message.setObjectName("cardHint")
        message.setWordWrap(True)
        layout.addWidget(message)
        risk = QLabel("即使有多帧核验，仍存在识别误判并误用“大胆整理”的风险。")
        risk.setObjectName("helper")
        risk.setWordWrap(True)
        layout.addWidget(risk)
        self.acknowledge_check = QCheckBox("我确认现在执行真实清理，并承担不可逆风险")
        layout.addWidget(self.acknowledge_check)
        actions = QHBoxLayout()
        actions.addStretch(1)
        cancel_button = QPushButton("取消")
        cancel_button.clicked.connect(self.reject)
        actions.addWidget(cancel_button)
        self.confirm_button = QPushButton("开始真实测试")
        self.confirm_button.setObjectName("dangerButton")
        self.confirm_button.setEnabled(False)
        self.confirm_button.clicked.connect(self.accept)
        actions.addWidget(self.confirm_button)
        layout.addLayout(actions)
        self.acknowledge_check.toggled.connect(self.confirm_button.setEnabled)
