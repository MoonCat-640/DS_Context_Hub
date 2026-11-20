"""Qt 桌面界面。主线程维护会话选择和窗口状态，后台线程负责读包、模型调用与导出。"""

import asyncio
import sqlite3
import sys
from dataclasses import dataclass, field
from pathlib import Path
from zipfile import BadZipFile

from cryptography.exceptions import InvalidTag
from PySide6.QtCore import Qt, QThread, QUrl, Signal
from PySide6.QtGui import QDesktopServices, QFont, QIcon
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QDialog, QFileDialog, QFormLayout, QHeaderView,
    QHBoxLayout, QInputDialog, QLabel, QLineEdit, QListWidget, QMainWindow,
    QMessageBox, QPlainTextEdit, QProgressBar, QPushButton, QSplitter,
    QTabWidget, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget,
)

from . import vault
from .archive import read_archive
from .export import GUIDES, new_batch, write_bundle
from .providers import (
    PREFERRED_MODELS, PROVIDERS, Provider, compact, error_message, estimate_tokens, generator, validate_key,
)


# 命名控件使用 #primary、#heading 等选择器，多个页面共用同一套 Qt 样式。
STYLE = """
QWidget { background: #202124; color: #e8eaed; }
QLabel#heading { font-size: 26px; font-weight: 600; }
QLabel#muted { color: #bdc1c6; }
QTabWidget::pane { border: 1px solid #3c4043; border-radius: 7px; }
QTabBar::tab { background: #292a2d; padding: 9px 22px; margin-right: 3px;
    border-top-left-radius: 6px; border-top-right-radius: 6px; }
QTabBar::tab:selected { background: #373b42; color: #a8c7fa; }
QPushButton, QComboBox { background: #35363a; border: 1px solid #50535a;
    border-radius: 6px; padding: 7px 13px; }
QPushButton:hover, QComboBox:hover { background: #42454b; }
QPushButton#primary { background: #a8c7fa; color: #132746; border-color: #a8c7fa; font-weight: 600; }
QPushButton#primary:hover { background: #c2d7fa; }
QPushButton:disabled, QPushButton#primary:disabled { background: #2d2e31; color: #777b83; border-color: #3c4043; }
QPushButton:focus, QComboBox:focus, QLineEdit:focus { border-color: #a8c7fa; }
QLineEdit, QPlainTextEdit, QTreeWidget, QListWidget { background: #27282b;
    border: 1px solid #3c4043; border-radius: 6px; padding: 5px; selection-background-color: #354b65; }
QAbstractItemView { outline: none; }
QTreeWidget::item, QListWidget::item { padding: 5px; }
QTreeWidget::item:selected, QListWidget::item:selected { background: #354b65; }
QHeaderView::section { background: #292a2d; padding: 7px; border: 0; }
QSplitter::handle { width: 8px; }
QScrollBar:vertical { background: #27282b; width: 10px; }
QScrollBar:horizontal { background: #27282b; height: 10px; }
QScrollBar::handle { background: #53575e; border-radius: 4px; min-height: 22px; min-width: 22px; }
QScrollBar::add-line, QScrollBar::sub-line { width: 0; height: 0; }
QScrollBar::add-page, QScrollBar::sub-page { background: transparent; }
QProgressBar { border: 1px solid #3c4043; border-radius: 5px; text-align: center; }
QProgressBar::chunk { background: #315783; border-radius: 4px; }
"""


def label(text, name="muted"):
    """创建可换行的纯文本标签，避免外部文本被 Qt 解释为富文本。"""
    widget = QLabel(text)
    widget.setTextFormat(Qt.TextFormat.PlainText)
    widget.setObjectName(name)
    widget.setWordWrap(True)
    return widget


def button(text, action, primary=False):
    """把按钮绑定到回调，primary 对应样式表中的主要操作按钮。"""
    widget = QPushButton(text)
    widget.clicked.connect(action)
    if primary:
        widget.setObjectName("primary")
    return widget


class Job(QThread):
    """在后台运行一个任务。用 progress 通知进度，界面收到 finished 后取 result 或 error。"""

    progress = Signal(int, str)

    def __init__(self, task, parent):
        super().__init__(parent)
        self.task = task
        self.result = None
        self.error = None

    def run(self):
        try:
            self.result = self.task(self)
        except Exception as error:
            self.error = error
        finally:
            # 任务闭包可能引用整批会话和密钥，线程结束即可释放这份引用。
            self.task = None


@dataclass(frozen=True)
class Connection:
    """记录本次已验证的平台、模型和接续工具。repr=False 避免打印配置时显示密钥。"""

    platform: str
    key: str = field(repr=False)
    harness: str
    provider: Provider


class Settings(QDialog):
    """在使用会话正文前检测密钥。通过后将实际可用的连接配置交给主窗口。"""

    def __init__(self, parent, config=None):
        super().__init__(parent)
        self.setWindowTitle("配置模型与接续工具")
        self.setMinimumWidth(470)
        self.config = config
        self.job = None
        self.platform = QComboBox()
        self.platform.addItems(PROVIDERS.keys())
        self.harness = QComboBox()
        self.harness.addItems(GUIDES.keys())
        self.key = QLineEdit()
        self.key.setEchoMode(QLineEdit.EchoMode.Password)
        self.key.setPlaceholderText("输入所选平台的 API Key")
        self.model = label("")
        self.remember = QCheckBox("使用主密码加密保存 API Key")
        self.status = label("检测会向平台发送一条简短测试消息，可能消耗少量额度。")
        self.platform.currentTextChanged.connect(self.platform_changed)
        if config:
            self.platform.setCurrentText(config.platform)
            self.key.setText(config.key)
            self.harness.setCurrentText(config.harness)
        self.update_model(self.platform.currentText())

        form = QFormLayout()
        form.addRow("模型平台", self.platform)
        form.addRow("默认模型", self.model)
        form.addRow("API Key", self.key)
        form.addRow("接续工具", self.harness)
        self.unlock_button = button("解锁已存密钥", self.unlock)
        self.verify_button = button("检测并确认", self.verify, True)
        actions = QHBoxLayout()
        actions.addWidget(self.unlock_button)
        actions.addStretch()
        actions.addWidget(self.verify_button)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(21, 21, 21, 21)
        layout.setSpacing(13)
        layout.addLayout(form)
        layout.addWidget(self.remember)
        layout.addWidget(self.status)
        layout.addLayout(actions)

    def platform_changed(self, name):
        # 切换平台时清空输入，防止把上一个平台的密钥发往新的服务地址。
        self.key.clear()
        self.update_model(name)

    def update_model(self, name):
        default = PROVIDERS[name].model
        preferred = PREFERRED_MODELS.get(name)
        self.model.setText(f"{preferred} 或 {default}" if preferred else default)

    def password(self, prompt):
        value, ok = QInputDialog.getText(self, "密钥保险库", prompt, QLineEdit.EchoMode.Password)
        return value if ok and value else None

    def unlock(self):
        """从保险库取回密钥填入表单，模型访问权限仍由后续检测确认。"""
        password = self.password("输入此平台密钥的主密码")
        if password is None:
            return
        try:
            key = vault.load(vault.vault_path(), self.platform.currentText(), password)
        except InvalidTag:
            self.status.setText("主密码错误或保险库数据已损坏。")
            return
        except (OSError, ValueError, sqlite3.Error):
            self.status.setText("无法读取本地保险库。")
            return
        if key:
            self.key.setText(key)
            self.status.setText("已解锁，请检测密钥以确认模型权限。")
        else:
            self.status.setText("此平台尚未保存密钥。")

    def verify(self):
        """在界面线程收集输入，再在后台检测平台。只有勾选保存才会请求主密码。"""
        key = self.key.text().strip()
        if not key:
            self.status.setText("请先输入 API Key。")
            return
        platform, harness = self.platform.currentText(), self.harness.currentText()
        password = None
        if self.remember.isChecked():
            password = self.password("设置至少 10 个字符的主密码")
            if password is None:
                return
            if len(password) < 10:
                self.status.setText("主密码至少需要 10 个字符。")
                return
            if password != self.password("再输入一次主密码"):
                self.status.setText("两次主密码输入不一致。")
                return

        def verify_task(_job):
            provider = asyncio.run(validate_key(platform, key))
            saved = True
            if password:
                # 网络验证和本地保存独立处理，写库失败时密钥仍可在本次运行中使用。
                try:
                    vault.save(vault.vault_path(), platform, key, password)
                except (OSError, ValueError, sqlite3.Error):
                    saved = False
            return Connection(platform, key, harness, provider), saved

        self.job = Job(verify_task, self)
        self.job.finished.connect(self.verified)
        self.form_state(False)
        self.status.setText("正在检测密钥和模型权限…")
        self.job.start()

    def form_state(self, enabled):
        # 检测进行中锁定相关输入，避免请求返回时平台或密钥已经改变。
        for widget in (self.platform, self.harness, self.key, self.remember, self.unlock_button, self.verify_button):
            widget.setEnabled(enabled)

    def verified(self):
        """回到界面线程后展示验证结果，验证通过才接受这个对话框。"""
        job, self.job = self.job, None
        job.deleteLater()
        self.form_state(True)
        if job.error:
            self.status.setText(error_message(job.error))
            QMessageBox.warning(self, "API Key 检测失败", error_message(job.error))
            return
        self.config, saved = job.result
        if not saved:
            QMessageBox.warning(self, "密钥保存失败", "API Key 可以使用，但无法写入本地保险库。")
        self.accept()

    def reject(self):
        # 对话框持有线程对象，等检测结束后再允许关闭。
        if self.job is None:
            super().reject()


class Window(QMainWindow):
    """管理导入、预览和导出的顺序。self.job 指向当前读包或压缩任务。"""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("DS Context Hub")
        self.resize(1120, 710)
        self.setMinimumSize(780, 540)
        self.sessions = []
        self.config = None
        self.destination = None
        self.batch = None
        self.job = None

        central = QWidget()
        root = QVBoxLayout(central)
        root.setContentsMargins(25, 19, 25, 19)
        root.setSpacing(12)
        header = QHBoxLayout()
        header.addWidget(label("DS Context Hub", "heading"))
        header.addStretch()
        self.settings_button = button("模型与接续设置", self.settings)
        header.addWidget(self.settings_button)
        root.addLayout(header)
        self.tabs = QTabWidget()
        root.addWidget(self.tabs)
        self.make_selection_tab()
        self.make_output_tab()
        self.setCentralWidget(central)

    def make_selection_tab(self):
        """连接搜索、勾选和预览。点中某一行用于预览，勾选才会进入导出批次。"""
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)
        toolbar = QHBoxLayout()
        self.import_button = button("打开 DeepSeek ZIP", self.open_archive, True)
        toolbar.addWidget(self.import_button)
        self.source_label = label("选择从 DeepSeek 网页导出的 ZIP 文件")
        toolbar.addWidget(self.source_label, 1)
        layout.addLayout(toolbar)

        splitter = QSplitter()
        splitter.setHandleWidth(12)
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        self.search = QLineEdit()
        self.search.setPlaceholderText("按标题搜索")
        self.search.textChanged.connect(self.filter_list)
        left_layout.addWidget(self.search)
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["会话标题", "消息"])
        header = self.tree.header()
        header.setStretchLastSection(False)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.tree.setRootIsDecorated(False)
        self.tree.setUniformRowHeights(True)
        self.tree.currentItemChanged.connect(self.preview_item)
        self.tree.itemChanged.connect(self.selection_changed)
        left_layout.addWidget(self.tree, 1)
        selection = QHBoxLayout()
        selection.addWidget(button("勾选可见", lambda: self.check_visible(True)))
        selection.addWidget(button("清除可见", lambda: self.check_visible(False)))
        selection.addStretch()
        left_layout.addLayout(selection)
        splitter.addWidget(left)

        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        self.preview_title = label("清洗后预览")
        right_layout.addWidget(self.preview_title)
        self.preview = QPlainTextEdit()
        self.preview.setReadOnly(True)
        self.preview.setPlaceholderText("选择左侧会话以查看内容")
        right_layout.addWidget(self.preview, 1)
        splitter.addWidget(right)
        splitter.setSizes([350, 690])
        splitter.setStretchFactor(1, 1)
        layout.addWidget(splitter, 1)
        self.selection_label = label("已勾选 0 条")
        layout.addWidget(self.selection_label)
        self.tabs.addTab(page, "会话")

    def make_output_tab(self):
        """组装输出目录、预计发送的平台信息和每条会话的完成状态。"""
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(12)
        row = QHBoxLayout()
        self.choose_button = button("选择输出目录", self.choose_directory)
        row.addWidget(self.choose_button)
        self.destination_label = label("尚未选择输出目录")
        row.addWidget(self.destination_label, 1)
        layout.addLayout(row)
        self.transfer = label("开始后，所勾选会话的清洗文本将发送到所选平台，可能产生 API 费用。")
        layout.addWidget(self.transfer)
        self.progress = QProgressBar()
        self.progress.setValue(0)
        layout.addWidget(self.progress)
        self.results = QListWidget()
        layout.addWidget(self.results, 1)
        self.output_status = label("在会话页勾选要接续的聊天。")
        layout.addWidget(self.output_status)
        row = QHBoxLayout()
        self.open_button = button("打开输出文件夹", self.open_batch)
        self.open_button.setEnabled(False)
        self.cancel_button = button("停止批次", self.stop_batch)
        self.cancel_button.setEnabled(False)
        self.start_button = button("开始压缩", self.start, True)
        self.start_button.setEnabled(False)
        row.addWidget(self.open_button)
        row.addStretch()
        row.addWidget(self.cancel_button)
        row.addWidget(self.start_button)
        layout.addLayout(row)
        self.tabs.addTab(page, "压缩与导出")

    def settings(self):
        """仅在对话框接受时替换连接配置，并在输出页显示本次实际使用的模型。"""
        dialog = Settings(self, self.config)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.config = dialog.config
            platform, harness = self.config.platform, self.config.harness
            self.settings_button.setText(f"{platform} · {harness}")
            self.transfer.setText(
                f"清洗文本将发送至 {platform}（{self.config.provider.model}），可能产生 API 费用。\n{GUIDES[harness]}"
            )
            return True
        return False

    def open_archive(self):
        """把读包交给后台任务，期间禁用会与本次导入冲突的操作。"""
        path, _ = QFileDialog.getOpenFileName(self, "打开 DeepSeek 导出文件", "", "ZIP (*.zip)")
        if not path:
            return
        self.import_button.setEnabled(False)
        self.settings_button.setEnabled(False)
        self.start_button.setEnabled(False)
        self.source_label.setText("正在读取会话…")
        self.job = Job(lambda _job: read_archive(Path(path)), self)
        self.job.finished.connect(self.archive_read)
        self.job.start()

    def archive_read(self):
        """成功后才替换已有会话列表，读包失败时仍可继续处理上一份数据。"""
        job, self.job = self.job, None
        job.deleteLater()
        self.import_button.setEnabled(True)
        self.settings_button.setEnabled(True)
        if job.error:
            self.source_label.setText(f"已加载 {len(self.sessions)} 条会话")
            detail = (
                "找不到有效的 DeepSeek 会话索引。"
                if isinstance(job.error, (ValueError, BadZipFile)) else "无法读取该 ZIP，请检查文件和访问权限。"
            )
            QMessageBox.warning(self, "导入失败", detail)
            self.selection_changed()
            return
        self.sessions, skipped = job.result
        # 批量填充时暂停列表信号。UserRole 存会话索引，重名标题也能定位到正确正文。
        self.tree.blockSignals(True)
        self.tree.clear()
        for index, session in enumerate(self.sessions):
            item = QTreeWidgetItem([session.title, str(session.turns)])
            item.setData(0, Qt.ItemDataRole.UserRole, index)
            if session.text:
                item.setCheckState(0, Qt.CheckState.Unchecked)
            else:
                item.setDisabled(True)
                item.setToolTip(0, "此会话清洗后无可用文本")
            self.tree.addTopLevelItem(item)
        self.tree.blockSignals(False)
        self.preview.clear()
        self.preview_title.setText("清洗后预览")
        self.source_label.setText(f"已加载 {len(self.sessions)} 条会话，跳过 {skipped} 条无法解析的会话")
        self.filter_list()
        self.selection_changed()
        if self.sessions and self.config is None:
            self.settings()

    def preview_item(self, item, _previous):
        """长对话只截取屏幕预览，长度估算和实际压缩使用完整会话。"""
        if item is None:
            self.preview.clear()
            self.preview_title.setText("清洗后预览")
            return
        session = self.sessions[item.data(0, Qt.ItemDataRole.UserRole)]
        excerpt = session.text[:35000]
        if len(excerpt) < len(session.text):
            excerpt += "\n\n［预览已截断，压缩使用完整清洗文本］"
        self.preview.setPlainText(excerpt)
        self.preview_title.setText(f"输入 Token 保守估计 ≤ {estimate_tokens(session.text):,}")

    def items(self):
        return (self.tree.topLevelItem(index) for index in range(self.tree.topLevelItemCount()))

    def filter_list(self):
        # 搜索只影响可见性，临时隐藏的行保留原来的勾选状态。
        query = self.search.text().strip().casefold()
        for item in self.items():
            item.setHidden(query not in item.text(0).casefold())

    def check_visible(self, checked):
        """批量修改当前可见且可用的行，然后统一刷新勾选计数。"""
        self.tree.blockSignals(True)
        for item in self.items():
            if not item.isHidden() and not item.isDisabled():
                item.setCheckState(0, Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked)
        self.tree.blockSignals(False)
        self.selection_changed()

    def selection(self):
        """返回所有已勾选的有效会话，包括被当前搜索条件暂时隐藏的条目。"""
        return [
            self.sessions[item.data(0, Qt.ItemDataRole.UserRole)] for item in self.items()
            if item.checkState(0) == Qt.CheckState.Checked and not item.isDisabled()
        ]

    def selection_changed(self, *_args):
        # 这里只判断勾选与忙碌状态，模型设置和输出目录允许在开始时再补齐。
        count = len(self.selection())
        self.selection_label.setText(f"已勾选 {count} 条")
        self.start_button.setEnabled(self.job is None and count > 0)

    def choose_directory(self):
        path = QFileDialog.getExistingDirectory(self, "选择输出目录", str(self.destination or Path.home()))
        if path:
            self.destination = Path(path)
            self.destination_label.setText(path)
        return bool(self.destination)

    def start(self):
        """确认本次发送的平台和会话数后，才创建批次目录并启动压缩。"""
        selected = self.selection()
        if not selected or self.job:
            return
        if not self.config and not self.settings():
            return
        if not self.destination and not self.choose_directory():
            return
        connection = self.config
        consent = QMessageBox.question(
            self, "开始模型压缩",
            f"将发送 {len(selected)} 条会话的清洗文本至 {connection.platform}（{connection.provider.model}）。\n是否开始？",
        )
        if consent != QMessageBox.StandardButton.Yes:
            return
        try:
            batch = new_batch(self.destination)
        except OSError:
            QMessageBox.warning(self, "无法写入", "请重新选择有写入权限的输出目录。")
            return
        self.batch = batch
        self.results.clear()
        self.progress.setRange(0, len(selected))
        self.progress.setValue(0)
        self.output_status.setText("正在连接模型…")
        # 后台使用启动时确定的会话、连接和目录，后续界面选择只影响下一批。
        self.job = Job(
            lambda job: asyncio.run(self.process(job, selected, connection, batch)), self,
        )
        self.job.progress.connect(self.update_progress)
        self.job.finished.connect(self.export_finished)
        self.set_busy(True)
        self.job.start()

    @staticmethod
    async def process(job, selected, connection, batch):
        """一批复用一个客户端。每条成功就写盘，返回成功数、已处理数和批次总数。"""
        successes = 0
        completed = 0
        async with generator(connection.provider, connection.key) as generate:
            async def checked_generate(*args):
                # 停止是协作式的。请求已发出时等待它返回，再停止后续分段与写盘。
                if job.isInterruptionRequested():
                    raise asyncio.CancelledError
                response = await generate(*args)
                if job.isInterruptionRequested():
                    raise asyncio.CancelledError
                return response

            for index, session in enumerate(selected, 1):
                def update(message):
                    job.progress.emit(-1, f"{index}/{len(selected)} · {message}")

                try:
                    update("正在生成简报")
                    summary = await compact(checked_generate, connection.provider, session.text, update)
                    write_bundle(batch, index, session.title, summary, connection.harness)
                except asyncio.CancelledError:
                    break
                except OSError:
                    # 记录单条失败并继续处理其他会话，已完成的输出仍在批次目录中。
                    job.progress.emit(index, f"失败 · {session.title} · 无法写入导出文件")
                except Exception as error:
                    job.progress.emit(index, f"失败 · {session.title} · {error_message(error)}")
                else:
                    successes += 1
                    job.progress.emit(index, f"完成 · {session.title}")
                completed = index
        return successes, completed, len(selected)

    def update_progress(self, index, message):
        """负索引表示分段处理中的文字提示，非负索引表示一条会话已有最终结果。"""
        if index < 0:
            if self.job and not self.job.isInterruptionRequested():
                self.output_status.setText(message)
        else:
            self.progress.setValue(index)
            self.results.addItem(message)
            self.results.scrollToBottom()

    def set_busy(self, busy):
        self.import_button.setEnabled(not busy)
        self.settings_button.setEnabled(not busy)
        self.choose_button.setEnabled(not busy)
        self.cancel_button.setEnabled(busy)
        self.open_button.setEnabled(not busy and self.batch is not None)
        self.selection_changed()

    def stop_batch(self):
        if self.job:
            self.job.requestInterruption()
            self.cancel_button.setEnabled(False)
            self.output_status.setText("正在停止，将等待当前请求返回。")

    def export_finished(self):
        """按任务返回的计数区分失败与未处理，停止后仍能打开已有的批次结果。"""
        job, self.job = self.job, None
        job.deleteLater()
        self.set_busy(False)
        if job.error:
            self.output_status.setText(error_message(job.error))
        else:
            successes, completed, total = job.result
            self.output_status.setText(
                f"成功 {successes} 条，失败 {completed - successes} 条，未处理 {total - completed} 条。"
            )

    def open_batch(self):
        if self.batch:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.batch)))

    def closeEvent(self, event):
        # 窗口拥有线程对象。压缩时请求停止，读包时等待完成，等线程结束后才允许关闭。
        if self.job:
            if self.cancel_button.isEnabled():
                self.stop_batch()
            event.ignore()
        else:
            super().closeEvent(event)


def create_application(argv):
    """正常启动和发行自检共用同一套字体、样式和窗口图标。"""
    app = QApplication(argv)
    app.setStyle("Fusion")
    app.setFont(QFont("Microsoft YaHei UI", 10))
    app.setStyleSheet(STYLE)
    # 源码从仓库的 assets 读取，PyInstaller 在 _internal 下保留同样的相对位置。
    icon_path = Path(__file__).resolve().parents[1] / "assets" / "ds-context-hub.ico"
    app.setWindowIcon(QIcon(str(icon_path)))
    return app


def main():
    """显示主窗口并进入事件循环。源码入口与 Windows 可执行文件都调用这里。"""
    app = create_application(sys.argv)
    window = Window()
    window.show()
    sys.exit(app.exec())
