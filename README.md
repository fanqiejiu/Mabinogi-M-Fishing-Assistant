# 洛奇 M 钓鱼助手

<p align="center">
  <img src="fishing_assistant/assets/tomato_fish_icon.png" width="112" alt="番茄鱼项目图标">
</p>

<p align="center">本地运行的屏幕识别钓鱼辅助工具 · v0.2.1 · by 番茄啾</p>

> 通过识别右下角圆形钓鱼按钮的画面状态，判断上钩、续钓与原地失效状态；不依赖固定 14 秒等待时间，因此可自然覆盖等待更久的鱼。

## 特性

- **三态画面识别**：区分普通等待/抛竿、上钩鱼体和原地失效指针，避免把普通图标的红色区域当成上钩。
- **自动续钓与恢复**：收鱼后自动发送 `Space`；识别到原地失效指针后，按一次 `W → S` 恢复状态，再续钓。
- **商业化风格桌面界面**：支持日间/夜间模式，可保存显示器、分辨率和画面模式配置。
- **校准与可视化排查**：按 `F7` 校准按钮中心，按 `F9` 保存识别区域快照，便于调整范围。
- **本地诊断**：启动时一次性展示 CPU、显卡和内存型号；错误日志仅保存在本机，可由用户主动打包发送给作者。
- **GitHub 更新检查**：在设置页填写 `owner/repository` 后，可手动检查 Latest Release，或选择启动后自动检查。
- **易于扩展**：识别引擎、配置、诊断、更新检查和 PySide6 界面分离，后续可添加 OCR、多方案、统计或窗口定位。

## 系统要求

- Windows 10/11
- Python 3.10–3.13（源码运行或自行打包时需要）
- 游戏以窗口、无边框全屏或独占全屏方式运行，且右下角钓鱼按钮可见

## 快速开始

### 源码运行

1. 克隆或下载本仓库。
2. 双击 `setup.bat`，它会创建隔离的 `.venv` 并安装依赖。
3. 双击 `run.bat` 启动应用。
4. 在“控制台”选择游戏所在显示器、画面模式和分辨率。
5. 将鼠标放在右下角圆形钓鱼按钮**正中心**，点击“校准当前鼠标位置”或按 `F7`。
6. 可选：按 `F9` 保存识别区域快照，确认圆形按钮未被截断。
7. 保持游戏在前台，点击“开始监测”或按 `F8`。

### 打包 EXE

运行 `build.bat` 会生成 `dist\MabinogiFishingHelper.exe`。由于 EXE 包含 Qt 和 OpenCV，建议将其作为 GitHub Release 附件发布，而不是提交到源码仓库。

## 快捷键

| 快捷键 | 作用 |
| --- | --- |
| `F7` | 将当前鼠标位置记录为钓鱼按钮中心 |
| `F8` | 开始 / 暂停监测 |
| `F9` | 保存当前识别区域快照 |
| `Esc` | 紧急停止监测 |

## 识别逻辑与调节

默认参数基于参考画面设置：普通抛竿约 `766 px`、原地失效指针约 `365 px`、上钩鱼体约 `1985 px`。默认上钩阈值为 `1200 px`。

若游戏 UI 缩放、色彩、分辨率或按钮位置改变，请先重新校准。仍有偏差时，可在“识别与显示”页调整：

- **漏掉上钩**：适当降低“鱼体判定阈值”，如 `1000 px`。
- **普通抛竿被误判**：提高阈值，如 `1450 px`。
- **恢复未触发**：扩大“失效指针”像素范围，或检查快照是否完整覆盖按钮。
- **按钮被截断**：增大识别区域宽度/高度后重新校准。

程序只在确认状态满足连续帧条件后发送一次按键，并使用冷却时间避免重复触发。

## 设置、日志与隐私

- 本地钓鱼配置保存在项目目录的 `fishing_config.json`，不会提交至 Git。
- 错误日志和用户主动生成的诊断 ZIP 保存于 `%LOCALAPPDATA%\MabinogiFishingHelper\`。
- 诊断信息只包含应用错误、版本及启动时读取的一次性硬件型号；**不会自动上传、发送或持续监控**。
- GitHub 更新检查默认指向本仓库；仅在用户点击检查（或启用自动检查）时访问 GitHub Latest Release API。

## 项目结构

```text
fishing_assistant/
  app.py             # 应用生命周期与启动页
  config.py          # 版本化本地配置
  constants.py       # 应用版本、作者和资源路径
  diagnostics.py     # 本地错误日志与诊断包
  engine.py          # 屏幕识别、按键和全局快捷键
  splash.py          # 启动页
  system_profile.py  # 一次性硬件信息读取
  ui.py              # PySide6 桌面界面
  updates.py         # GitHub Release 更新检查
  assets/            # 项目图标
tests/               # 核心识别逻辑回归测试
```

## 开发验证

```powershell
.\.venv\Scripts\python.exe -m compileall fishing_assistant mabinogi_fishing_helper.py
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe -m pip check
```

## 许可证

本项目采用 [MIT License](LICENSE)。
