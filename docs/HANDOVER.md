# DS Context Hub 开发交接

交接基线为 **v0.1.2**，面向 Windows 10/11 x64，源码采用 MIT 许可证。应用读取 DeepSeek 网页端导出的 ZIP，供用户预览和勾选会话，再用其选择的模型生成 Markdown 接续简报。这一版引入蓝鲸图标，同一份 ICO 用于程序、窗口和安装快捷方式。[版本源码](https://github.com/MoonCat-640/DS_Context_Hub/tree/v0.1.2) · [发行附件](https://github.com/MoonCat-640/DS_Context_Hub/releases/tag/v0.1.2)

## 启动开发环境

在仓库根目录用 PowerShell 执行以下命令。日常开发支持 64 位 Python 3.11 及以上，下面使用与发行构建相同的 3.13 系列。

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m ds_context_hub
```

从源码启动时，`ds_context_hub/__main__.py` 进入 `ui.main()`。双击打包后的 `ds_context_hub.exe` 时，`packaging/launcher.py` 进入同一个窗口。给 exe 传入 `--self-test <报告路径>` 会改为运行离线自检。

## 跟读一次会话导出

| 步骤 | 代码入口 | 接手时应掌握的行为 |
| --- | --- | --- |
| 打开 ZIP | `archive.py` 的 `read_archive()`、`_conversation()` | 根据 `chat_session_index.json` 找会话，从 `current_message_id` 沿 `parent_id` 回溯后翻转顺序。重新生成的旧回答属于其他分支。单个 JSON 上限为 64 MiB。索引损坏会终止整次导入，个别会话损坏只增加跳过计数。 |
| 清洗与勾选 | `archive.py` 的 `clean_text()`，`ui.py` 的 `Window` | 账户文件 `user.json` 在读取前排除。清洗保留普通代码块、JSON 示例和附件提示。搜索只隐藏行，已经勾选的隐藏会话仍会导出。窗口预览截取前 35,000 个字符，模型接收完整清洗文本。 |
| 配置模型和密钥 | `providers.py` 的 `validate_key()`、`generator()`，`vault.py` | 密钥检测使用固定短消息。平台配置可使用 OpenAI 兼容接口或 Gemini、Claude 原生 SDK。有首选模型的平台只在 403 或 404 时尝试备用模型。成功后的实际模型会显示在输出页。 |
| 压缩 | `ui.py` 的 `Window.process()`，`providers.py` 的 `compact()` | Qt 后台线程运行异步请求，一批会话共用客户端。按 UTF-8 字节数保守估计正文长度，超出预算时分段再合并，最多八轮。合并后仍超预算且不再缩短时提前失败。用户停止批次时，已发出的请求会等到返回。 |
| 写出简报 | `export.py` 的 `new_batch()`、`write_bundle()` | 每批用独立目录，每条成功会话写入 `CONTEXT.md`、工具入口和 `接续说明.txt`。Claude Code 使用 `CLAUDE.md` 中的 `@CONTEXT.md`，另三种工具使用 `AGENTS.md`。写入中断的目录标为 `.incomplete-*`。 |

表中的应用模块均在 `ds_context_hub/` 下。新增模型时先检查 `PROVIDERS`、请求参数、完成原因和输入输出预算。新增接续工具时同步修改 `MEMORY_FILES` 与 `GUIDES`，离线自检会遍历这两类配置对应的输出。

用户确认开始压缩后，应用才向所选平台发送会话正文。API Key 用于平台鉴权，默认只在内存中保存。用户选择持久化时，`vault.py` 用独立的随机盐、600,000 轮 PBKDF2-HMAC-SHA256 和 AES-256-GCM 写入每用户 SQLite 库，平台名参与认证。更改派生参数或表结构时要保留旧库的解锁或迁移路径。开发和发布测试使用合成会话，个人导出包、密钥库和真实简报不纳入 Git 或发行附件。

## 蓝鲸图标

| 位置 | 用途 |
| --- | --- |
| `assets/ds-context-hub.png` | 1254 × 1254 的透明高清原稿。钴蓝鲸身和冰蓝色折页腹部对应会话归档。 |
| `assets/ds-context-hub.ico` | 16、20、24、32、40、48、64、96、128、256 像素十档，用于 Windows 缩放。 |
| `packaging/ds_context_hub.spec`、`ui.create_application()` | 构建时嵌入 exe，同时把 ICO 装入 `_internal/assets/`。Qt 从这里加载窗口图标。 |
| `packaging/installer.nsi` | 将 ICO 嵌入安装器与卸载器。桌面和开始菜单快捷方式启动 `ds_context_hub.exe`，图标位置显式指向安装目录下的 `_internal/assets/ds-context-hub.ico`。 |

更换图稿时，保留方形透明母版并更新其尺寸说明。在开发虚拟环境执行下面的命令，然后一起提交 PNG 和 ICO。Pillow 仅用于重新导出图标。

```powershell
.\.venv\Scripts\python.exe -m pip install Pillow
.\.venv\Scripts\python.exe packaging\make_icon.py
```

<details>
<summary>高清原稿的生成提示词（内置 ImageGen）</summary>

为 DS Context Hub 画一枚高清正方形 Windows 桌面图标，以 DeepSeek 的蓝鲸为灵感，创作独立的现代平面鲸鱼标记。鲸首圆润朝右、尾鳍向左上方扬起，紧凑饱满的剪影带一点向上游动的姿态。用明快的钴蓝作为主体，浅冰蓝的腹部弧面末端折起一个书页角，暗示会话归档。几何曲线干净，大色块，最多三种纯色，一个简洁的眼点。图形占画布约 85%，四周透明留白。在浅色和深色桌面上都醒目，缩小到 16 像素仍能认出鲸鱼。单枚独立标记，透明背景，无底板、文字、渐变、投影或水印。

</details>

## 构建、验证与发布

1. 日常运行使用 `requirements.txt`。制作发行版时单独建立 `.build-venv`，安装 `packaging/requirements-windows.lock` 并准备 NSIS 3.13。版本号同步更新 `packaging/build_windows.py` 和 `packaging/version_info.txt`，这样 ZIP 名、卸载登记和 exe 文件属性会一致。[Windows 构建步骤](https://github.com/MoonCat-640/DS_Context_Hub/blob/v0.1.2/packaging/README.md)
2. 运行下面的构建命令。`dist/ds_context_hub/` 是独立应用，`build/windows/frozen-self-test.json` 保存自检结果，`release/` 保存发行附件。首次构建及修改图标、源码或依赖后均执行完整冻结。

   ```powershell
   .\.build-venv\Scripts\python.exe packaging\build_windows.py --nsis build\tools\nsis-3.13\makensis.exe
   ```

3. 在 GitHub Actions 手动运行 `Verify Windows installer`，选择 `build` 可在干净的 Windows 机器从源码构建。它会以当前用户、全体用户两种范围安装到带中文和空格的新路径，从桌面和开始菜单启动并核对实际图标。测试会给桌面链接换上系统图标，再检查覆盖安装能否恢复蓝鲸，同时覆盖可选 PATH 和卸载。通过后可下载 `windows-release` 构件。日常开发机可直接运行打包程序的 `--self-test`，涉及系统注册表和快捷方式的完整安装测试留给测试机。[验证工作流](https://github.com/MoonCat-640/DS_Context_Hub/actions/workflows/verify-windows-installer.yml)
4. 为已验证的提交创建 `vX.Y.Z` Release，上传 `SHA256SUMS.txt` 和清单中的五个文件，即 `Setup.exe`、便携 ZIP、高清 PNG、多尺寸 ICO、`HANDOVER.md`。检查 GitHub 上的文件散列与清单一致。复验公开附件时选择工作流的 `release` 模式，填入标签和 `Setup.exe` 的 SHA-256。

## 排查入口

- **启动时缺少 Qt 插件或图标**。先运行打包版自检，查看报告中的异常信息。检查 `_internal` 文件夹是否完整，以及 spec 中的图标数据目标是否与窗口和快捷方式的路径一致。中文字体检查使用 Windows 原生 Qt 平台，强制设置 `QT_QPA_PLATFORM=offscreen` 会影响字体查找。
- **离线自检通过，但平台请求失败**。自检覆盖 SDK 初始化和合成分段流程。真实调用还取决于密钥、模型权限、额度与网络。界面只展示映射后的错误，排查时避免记录密钥或聊天正文。
- **卸载或重装行为异常**。`installer.nsi` 根据安装范围和路径识别已有副本，`PathEntry.cs` 记录本程序添加的 PATH 条目。重装使用原范围与原目录。卸载仅清理发行文件，用户数据和本地保险库会保留。安装包当前未签名，若 UAC 使用另一管理员账户的凭据，「当前用户」对应提权后的账户。
