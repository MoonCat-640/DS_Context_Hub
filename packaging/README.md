# Windows 构建

发行版面向 Windows 10/11 x64。构建使用 64 位 Python 3.13、PyInstaller 和 NSIS 3.13。`requirements-windows.lock` 固定本次验证的构建依赖，包括 PySide6 Essentials 6.9.2。

## 构建步骤

在项目根目录创建独立环境，然后从 [NSIS 官网](https://nsis.sourceforge.io/Download) 下载便携版编译器并解压到 `build/tools`。

```powershell
py -3.13 -m venv .build-venv
.\.build-venv\Scripts\python.exe -m pip install -r packaging\requirements-windows.lock
.\.build-venv\Scripts\python.exe packaging\build_windows.py --nsis build\tools\nsis-3.13\makensis.exe
```

构建脚本会生成独立应用目录、收集第三方许可证、运行打包后自检，再编译安装包并计算校验和。发布文件位于 `release`。

| 文件 | 用途 |
| --- | --- |
| `Setup.exe` | 内置全部依赖的离线安装包 |
| `DS_Context_Hub-0.1.0-windows-x64.zip` | 解压即可运行的便携版 |
| `SHA256SUMS.txt` | 两个发行文件的 SHA-256 校验和 |

`dist/ds_context_hub/ds_context_hub.exe` 是独立运行入口。同目录的 `_internal` 包含运行时支持文件。构建器只将该应用目录加入安装包及便携 ZIP。

## 安装行为

安装器请求管理员权限，再显示语言、许可证、安装范围、目录及组件页面。当前用户模式将快捷方式和卸载信息写入当前账户，全体用户模式写入公共位置。若标准用户在 UAC 中使用另一管理员账户的凭据，当前用户模式对应的是该管理员账户。

「添加安装目录到 PATH」默认关闭。选中后，安装器使用内置的 .NET Framework 小程序读写完整注册表值，并记录新增条目的归属。卸载只移除本程序添加的条目，保留已有 PATH 内容。安装与卸载均会检查目标程序是否正在运行。

卸载文件列表从实际发布目录生成，逐一删除程序文件。用户后来放入安装目录的其他文件和个人密钥保险库会保留。

## 验证与发布

打包后的 `--self-test <报告路径>` 使用合成会话验证 Qt 显示、消息分支、四种导出、所有平台 SDK 客户端初始化、分段摘要、SQLite 和加密。它在清除 Python 和 Qt 环境变量、从 PATH 移除开发工具后运行。结果写入 `build/windows/frozen-self-test.json`。

`Verify Windows installer` 工作流接受发行标签和安装包 SHA-256，在全新的 Windows 测试机下载安装包。它核验两种安装范围、自选中文路径、从开始菜单快捷方式启动、默认与可选 PATH、重复安装，以及卸载后保留用户文件、恢复 PATH。也可在干净的 Windows 测试机上以管理员身份运行 `packaging/verify_install.ps1`，加 `-ReviewWizard` 可手动查看向导。真实模型调用需要用户自己的有效 API Key。

将源码提交并推送后，以对应提交创建版本标签和 GitHub Release，上传 `release` 中的三个文件。当前构建不包含代码签名证书。
