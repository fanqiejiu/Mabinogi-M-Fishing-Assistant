# 洛奇 M 钓鱼助手

<p align="center">
  <img src="fishing_assistant/assets/tomato_fish_icon.png" width="112" alt="番茄鱼项目图标">
</p>

<p align="center">Windows 本地钓鱼辅助工具 · v0.5.4</p>

<p align="center">
  <a href="https://github.com/fanqiejiu/Mabinogi-M-Fishing-Assistant/releases">📥 下载 Release</a> ·
  <a href="#快速开始">🚀 快速开始</a> ·
  <a href="#常见情况">🛠️ 常见情况</a>
</p>

## 这是做什么的

洛奇 M 钓鱼助手读取右下角圆形按钮的画面，识别上钩、等待、原地失效和骑马图标，再按 `Space`、`W`、`S` 完成收鱼、续钓或恢复。

它先等待画面出现上钩图标，再根据所选模式判断收杆时机。模式 1 会追踪角色头顶绿条；模式 2 使用自定义计时；模式 3 上钩后立即收杆。

## 功能

- **三种收鱼方式**：模式 1 实验性识别体力条反弹，模式 2 固定计时，模式 3 上钩立即收杆。
- **跑鱼时间学习**：模式 1 检测到“讓牠跑掉了”后记录本轮耗时；下一轮识别仍失败时提前 1–2 秒兜底收杆。
- **自动收鱼与续钓**：上钩后收鱼，图标恢复后再抛竿。
- **原地恢复**：停留过久出现失效指针时，执行一次 `W → S`，再继续钓鱼。
- **骑马纠错**：检测到上马图标时不按 `Space`；检测到下马图标时只尝试一次下马。
- **OK 指定窗口模式（实验性）**：优先识别标题为“瑪奇 Mobile”的窗口；找不到时可手动选择。使用 WGC 截图和窗口消息，不会把按键发送给当前前台程序。
- **界面与排查工具**：支持日间/夜间主题、识别区域快照、本地错误日志和诊断包。
- **更新检查**：可在设置页手动检查 GitHub Release，也可选择启动后检查。

## 使用前说明

> [!CAUTION]
> 本工具仅识别现有游戏画面并模拟按键，不读取游戏内存、不修改游戏文件。请自行确认目标游戏的规则，并自行承担使用风险。

后台模式不是所有游戏或所有渲染环境都支持。洛奇 M 必须保持打开且不可最小化；如果后台截图正常但按键没有反应，切回“屏幕坐标模式”即可。

## 下载与运行

### 直接运行

在 [Releases](https://github.com/fanqiejiu/Mabinogi-M-Fishing-Assistant/releases) 下载 `ok-MabinogiFishing.exe`，解压后直接运行。

首次启动会短暂显示项目图标和版本号。配置、日志和诊断包均保存在本机。

### 源码运行

```powershell
git clone https://github.com/fanqiejiu/Mabinogi-M-Fishing-Assistant.git
cd Mabinogi-M-Fishing-Assistant
.\setup.bat
.\run.bat
```

系统要求：Windows 10/11、Python 3.10–3.13（仅源码运行或自行打包需要）。

## 快速开始

1. 进入游戏钓鱼场景，确保右下角圆形按钮完整可见。
2. 在“控制台”选择显示器、画面模式和游戏分辨率。
3. 默认使用“屏幕坐标模式”。把鼠标放到圆形按钮中心，点击校准或按 `F7`。
4. 按 `F9` 保存识别区域，确认按钮没有被截断。
5. 点击“开始监测”或按 `F8`。

想尝试后台模式时：选择“指定窗口后台模式” → 刷新窗口 → 选择“瑪奇 Mobile” → 选择“OK 后台引擎” → 在游戏内重新校准一次。

| 快捷键 | 作用 |
| --- | --- |
| `F7` | 校准钓鱼按钮中心 |
| `F8` | 开始 / 暂停监测 |
| `F9` | 保存当前识别区域 |
| `Esc` | 紧急停止 |

## 常见情况

| 情况 | 处理方式 |
| --- | --- |
| 漏掉上钩 | 在“识别与显示”中适当降低鱼体阈值，例如 `1000 px`。 |
| 普通抛竿被当成上钩 | 提高鱼体阈值，例如 `1450 px`。 |
| 识别区域不完整 | 调大识别区域后重新校准，再用 `F9` 检查快照。 |
| 切到浏览器后没有继续 | 选择“OK 后台引擎”，重新校准；仍无效则该环境不接受后台消息，请用屏幕坐标模式。 |
| 界面显示监测中但没有动作 | 查看本地错误日志或生成诊断包；失败时界面会自动切为已暂停。 |

## 数据与日志

- 钓鱼配置保存在项目目录的 `fishing_config.json`。
- 错误日志和诊断 ZIP 位于 `%LOCALAPPDATA%\MabinogiFishingHelper\`。
- 硬件型号只在启动时读取一次，用于诊断；不会持续监测。
- 不会自动上传日志或诊断包。
- 更新检查仅在手动触发或启用启动检查后访问 GitHub Latest Release API。

## 基于 ok-script

“OK 后台引擎”使用 [ok-script](https://github.com/ok-oldking/ok-script) 的 Windows Graphics Capture 与 PostMessage 组件实现。感谢 ok-script 提供的自动化框架与窗口后端能力。

本项目使用 `ok-script 2.0.6`，适用 Apache License 2.0 + Commons Clause 及附加条款。完整声明见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。

## 开发与打包

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\build.bat
```

打包结果为 `dist\ok-MabinogiFishing.exe`。EXE 包含 Qt、OpenCV 与 OK 框架依赖，建议作为 Release 附件，不要提交到源码仓库。

## 0.5.4 更新说明

这次主要把“正常抛竿”和“W → S 移动恢复”的先后顺序理顺了。正常情况下，按 F7 定位、F8 开始后，鱼竿图标一出现就会直接开始钓鱼。

1. 修复首次启动后明明已经出现鱼竿图标，却不立即按 Space，需要反复按 F7、F8 才能开始的问题。
2. 修复钓完一条鱼后，鱼竿图标已经恢复，脚本却又多执行一次 W → S 的问题。
3. 现在会区分“可以抛竿”和“已经抛竿、等待上钩”两个画面，避免按错 Space 或反复收杆。
4. W → S 只会在失效指针持续出现时使用；刚按过 Space 会留出短暂保护时间，减少画面切换造成的误判。
5. 监测过程中重新按 F7 定位后，会自动继续等待抛竿，不需要再次反复开关监测。

## 许可证

本项目采用 [MIT License](LICENSE)。第三方依赖按各自许可证分发和使用。