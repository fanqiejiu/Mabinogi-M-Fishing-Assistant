# 项目结构与代码导航

先按“改什么”找文件，不需要从几千行的主窗口或引擎文件开始翻。

## 目录总览

```text
fishing_assistant/
├── app.py                   应用入口：管理员检查、Qt 与应用生命周期
├── engine.py                FishingEngine：共享状态、线程、锁及生命周期
├── ui.py                    旧 UI 导入兼容入口，不放新逻辑
├── config.py                配置字段、默认值、校验和保存
├── constants.py             版本、资源路径及功能开关
├── desktop/                 桌面界面
│   ├── main_window.py       主窗口组装、Qt 信号、窗口关闭和最小化
│   ├── pages/               控制台、钓鱼、阈值、设置、使用说明的布局
│   ├── controllers/         配置联动、钓鱼设置、偏好、更新及事件展示
│   ├── widgets.py           卡片、折叠说明、防滚轮控件与状态标签
│   ├── forms.py             精简表单标题、悬停解释与可访问说明
│   ├── terminology.py       运行、捕获、输入和图标识别的公共显示名称
│   ├── design.py            字体层级、中文回退与公共卡片间距（Qt 逻辑像素）
│   ├── dialogs.py           更新、仅 W 模式、背包危险操作确认弹窗
│   ├── styles.py            日间、夜间和悬浮栏样式
│   └── floating_status.py   悬浮状态栏
├── automation/              自动化执行流程，不依赖桌面界面
│   ├── models.py            事件、状态枚举、识别结果数据
│   ├── tasks.py             校准、启停及钓鱼/制作/背包测试互斥
│   ├── pause.py             暂停/继续、任务占用及旧操作失效
│   ├── monitor.py           唯一监测线程、任务分发和钓鱼帧处理
│   ├── fishing.py           收杆策略、计时学习、反弹状态机
│   ├── recovery.py          续钓、W/S 恢复、骑马与异常提示保护
│   ├── inventory.py         背包整理流程及大胆整理关闭确认
│   ├── inventory_entry.py   识别背包当前页面，安全进入整理面板
│   ├── capture.py           截图、坐标换算和 OK 后台实例管理
│   ├── input.py             游戏按键、鼠标、后台悬停操作
│   ├── hotkeys.py           全局快捷键分发、按住去重及可选停止键
│   └── diagnostics.py       F9 和连续识别失败现场保存
├── vision/                  图片识别算法
│   ├── fishing_icons.py     钓鱼图标、指南针及手动选择的像素兼容识别
│   ├── ok_templates.py      OK 模板缓存、多尺度扫描、固定提示识别
│   ├── fishing_stamina.py   钓鱼体力槽与中点状态识别
│   └── ...                  既有校准、签名识别、体力条、诊断等模块
├── features/crafting/       自动制作的完整功能目录
│   ├── model.py             配方、用时、次数规则和纯状态机
│   ├── recognition.py       OK 加工界面与百分比识别
│   ├── queue_recognition.py  OK 队列格数、多行布局与槽位状态识别
│   ├── runner.py            队列执行、确认及停止保护
│   └── page.py              自动制作页面
├── features/fishing_history/钓鱼会话历史、SQLite 存储与统计页面
│   ├── store.py             会话持久化、异常中断恢复和累计统计
│   └── page.py              历史记录表格与统计展示
├── features/food/           食物制作预留页面，未开放识别或执行
├── window_target.py         Windows 窗口、WGC、PostMessage 适配
├── window_geometry.py       OK 客户区帧、物理像素/DPI 上下文和输入前几何校验
├── window_interaction.py    OK 客户区输入保护：悬停/按住、停止检查及消息失败上报
├── inventory_cleanup.py     背包整理界面识别，不负责执行清理
├── voice_alerts.py          音色扫描、随机选择和防重叠播放
├── updates.py              Release 查询与版本比较
├── diagnostics.py          通用日志和支持包工具
├── system_profile.py       本机诊断信息
├── startup_guard.py        管理员和多开检查
├── splash.py               启动展示
└── assets/                 识别模板及图标，路径保持不变
tests/                      回归测试
scripts/                    素材构建、离线识别和打包校验工具
docs/                       使用与开发文档
remote/                     预备 Android/中转项目，尚未默认启用
```

根目录的 `crafting.py`、`crafting_ui.py`、`crafting_runtime.py` 和 `crafting_vision.py` 也是兼容入口。新代码请直接导入 `features.crafting` 下的实际模块。

## 常见修改去哪里

| 想修改的内容 | 优先查看 |
| --- | --- |
| 钓鱼页面排版 | `desktop/pages/fishing.py` |
| 设置页、调试区排版 | `desktop/pages/settings.py` |
| 固定页内标签、分类独立滚动 | `desktop/pages/sectioned.py` 的 `SectionedPage`；只负责导航，不读写配置 |
| 模式选择后的显示/隐藏和安全提醒 | `desktop/controllers/fishing.py` |
| 分辨率、识别模式、配置加载和控件连接 | `desktop/controllers/configuration.py` |
| 字号、字体回退和公共卡片间距 | `desktop/design.py`；页面使用语义角色，不单独写字号 |
| 颜色、输入框外观 | `desktop/styles.py`、`desktop/widgets.py` |
| 窗口、捕获和图标识别的显示名称 | `desktop/terminology.py`；内部配置键保持不变 |
| 运行状态、语音触发、日志展示 | `desktop/controllers/events.py` |
| 语音设置、悬浮栏、主题切换 | `desktop/controllers/preferences.py` |
| 更新弹窗内容/更新检查交互 | `desktop/dialogs.py`、`desktop/controllers/services.py` |
| 使用说明 | `desktop/pages/help.py` 与 `docs/` |
| 自动制作子菜单 | `desktop/pages/crafting.py`；食物预留页在 `features/food/page.py` |
| 悬浮栏暂停/继续 | `desktop/floating_status.py`、`desktop/controllers/floating_controls.py`、`automation/pause.py` |
| 模式一/二/三的收杆策略 | `automation/fishing.py` |
| W/S、仅 W、重试上限或续钓 | `automation/recovery.py` |
| 图片匹配是否准确 | `vision/`；制作识别在 `features/crafting/recognition.py` |
| 后台截图/按键是否生效 | `automation/capture.py`、`automation/input.py`、`window_target.py` |
| 制作截图与点击坐标、窗口边框/DPI | `window_geometry.py`、`window_target.py` 的显式客户区通路 |
| 制作点击无响应、消息投递失败或点击期间暂停 | `window_interaction.py`；只扩展 OK 客户区通路，旧 F7 输入行为不变 |
| 背包安全确认和清理顺序 | `automation/inventory.py`；图片识别在 `inventory_cleanup.py` |
| 制作配方、时间、加工次数、队列容量 | `features/crafting/model.py`、`features/crafting/queue_recognition.py` |
| 新增配置项 | `config.py` → 对应页面 → 对应 controller → 对应流程 → 测试 |
| 全局停止快捷键 | `automation/hotkeys.py`；允许的键和默认值在 `config.py`，界面在设置常规页 |

## 调用关系和状态归属

`app.py` 创建一个 `FishingEngine` 和一个 `MainWindow`。界面通过引擎入口更改配置或启停任务，引擎通过 `EngineEvent` 把结果送回界面。界面不直接发送游戏按键。

引擎只有一个主监测线程。`automation/monitor.py` 分发钓鱼、制作和背包测试，不能为每个功能随意另开一套送键线程。截图和输入由窗口后端处理，识别模块只分析画面。

这次是**保留行为的职责拆分**，没有同时重写状态管理：

- `FishingEngine` 仍集中持有配置、锁、停止代次、模板缓存和钓鱼运行状态。
- `MainWindow` 仍持有控件和 Qt 信号。
- `*Mixin` 是这两个类内部的职责分块，不是独立服务；不单独实例化，不新增 `__init__`，不在多个分块中覆盖同名方法。修改时先看同文件顶部的职责说明。
- 带 `@classmethod` 的识别方法仍经 `FishingEngine` 调用，共用原来的阈值和缓存。不要直接实例化识别 mixin 建立另一份状态。
- 新的独立功能优先采用 `features/crafting/` 的结构：纯规则、识别、执行、页面分开。不要把功能继续塞回协调器。

这些分块还共享宿主状态，不声称已经完全解耦。后续若改成独立对象，应作为单独重构，有完整测试后再调整，避免把文件拆分和时序变化混在一次提交里。

## 兼容与安全边界

以下入口仍可使用，导出的是同一个类，不是复制的实现：

```python
from fishing_assistant.ui import MainWindow
from fishing_assistant.engine import FishingEngine, EngineEvent, EventKind, IconState
from fishing_assistant.crafting import CraftOptions, CraftSession
```

启动脚本、配置文件位置、配置字段、图片资源路径、版本号及 OK 默认识别策略均未因目录拆分而改变。预备远程功能开关仍为关闭。

内部函数移动后，测试的 `patch()` 要指向函数实际查找依赖的模块。例如更新检查应 patch `fishing_assistant.desktop.controllers.services.check_github_release`，F9 的目录应 patch `fishing_assistant.automation.diagnostics.VISION_DIAGNOSTICS_DIR`。旧入口保证类和数据类型的导入兼容，不保证把内部模块变量当作公开扩展点使用。

不要削弱以下规则：

- F8 / 用户设置的停止快捷键停止后，旧帧和旧任务不得继续送键。Esc 仅为默认值，关闭或改键后不再作为全局停止键；内部游戏 Esc 和合成事件防误触保持独立。
- 钓鱼、自动制作、背包测试不得并行操作游戏。
- OK 识别失败不能自动切回用户未选择的像素方案。
- 背包清理默认关闭；执行前反复确认大胆整理已经关闭，不确定就停止。
- 时间估计不能代替必要的画面确认。
- 自动制作使用 `ClientFrame`：OK 在物理像素上下文中测量客户区并裁掉边框，识别和后台输入共享该帧几何信息；输入前再核对客户区/DPI，不能按外框尺寸盲目缩放点击。旧 F7 外框坐标通路保留兼容，不能混用两种坐标。
- 导入模块、显示页面或运行离线测试不能自动开始钓鱼、清理背包或消耗制作材料。
- UI 窗口发现显式使用 `list_target_windows(include_minimized=True)` 标明最小化状态；运行通路维持默认排除最小化窗口。两个页面复用 `select_target_window` 保留用户选择，不能从无关窗口中默认选第一项。
- 主窗口构建页面前即应用已保存主题；首次显示与隐藏页面的调色板回归见 `tests/test_startup_presentation.py`，不能只验证手动切换后的界面。
- 钓鱼、应用设置使用 `SectionedPage` 组织子分类；页内导航固定、各分类保留各自滚动位置。导航和防滚轮标签只切换展示，不能触发配置保存或游戏任务。布局回归见 `tests/test_desktop_layout.py`。

## 打包自检

字体和间距统一由 `desktop/design.py` 定义。应用入口与自检入口使用同一个 `ui_font()`；页面、自动制作及悬浮栏复用语义字号。Qt 负责系统 DPI 缩放，不对游戏截图或客户区坐标应用 UI 缩放。`tests/test_desktop_typography.py` 在独立 Qt 进程中验证 100%、125%、150%、200% 缩放、双主题、选项文字与危险确认弹窗。

`desktop/bundle_check.py` 提供显式的 `--verify-bundle <报告路径>` 自检入口。它只构建界面、检查 Qt/OK 与资源，不启动全局热键、后台捕获、更新服务或游戏任务，也不保存用户配置。正式启动仍经过管理员与单实例检查。

详细开发流程见 [贡献指南](../CONTRIBUTING.md)。

界面文案的常驻提示、悬停解释和安全告知如何分层，见 [桌面文案约定](ui-copy.md)。
