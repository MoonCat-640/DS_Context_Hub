"""Offline checks executed inside the frozen executable during release builds."""

import asyncio
import json
import sys
import tempfile
import traceback
from pathlib import Path
from zipfile import ZipFile


def run(report: Path) -> int:
    results = {"frozen": bool(getattr(sys, "frozen", False)), "executable": str(Path(sys.executable).resolve()), "checks": []}
    try:
        from PySide6.QtCore import Qt
        from PySide6.QtGui import QFont, QFontMetrics
        from PySide6.QtWidgets import QApplication, QTreeWidgetItem
        from cryptography.exceptions import InvalidTag
        from ds_context_hub import vault
        from ds_context_hub.archive import read_archive
        from ds_context_hub.export import MEMORY_FILES, new_batch, write_bundle
        from ds_context_hub.providers import PROVIDERS, compact, generator
        from ds_context_hub.ui import STYLE, Window

        app = QApplication([])
        app.setStyle("Fusion")
        app.setStyleSheet(STYLE)
        app.setFont(QFont("Microsoft YaHei UI", 10))
        assert QFontMetrics(app.font()).inFont("中")
        window = Window()
        with tempfile.TemporaryDirectory(prefix="ds-hub-self-test-") as temporary:
            root = Path(temporary)
            archive = root / "fixture.zip"
            messages = [
                {"id": 1, "parent_id": None, "role": "USER", "fragments": [
                    {"type": "REQUEST", "content": "保存关键代码\n" * 3500},
                ]},
                {"id": 2, "parent_id": 1, "role": "ASSISTANT", "fragments": [
                    {"type": "RESPONSE", "content": "obsolete branch"},
                ]},
                {"id": 3, "parent_id": 1, "role": "ASSISTANT", "fragments": [
                    {"type": "RESPONSE", "content": "current decision"},
                    {"type": "TEMPLATE_RESPONSE", "content": "busy"},
                ]},
            ]
            with ZipFile(archive, "w") as zipped:
                zipped.writestr("user.json", "account data is intentionally invalid JSON")
                zipped.writestr("chat_session_index.json", json.dumps([{"id": "demo", "title": "安装验证"}]))
                zipped.writestr("sessions/demo.json", json.dumps({"id": "demo", "current_message_id": 3, "messages": messages}))
            sessions, skipped = read_archive(archive)
            assert len(sessions) == 1 and skipped == 0
            assert "obsolete branch" not in sessions[0].text
            assert "current decision" in sessions[0].text
            results["checks"].append("archive and active branch")
            window.sessions = sessions
            item = QTreeWidgetItem([sessions[0].title, str(sessions[0].turns)])
            item.setData(0, Qt.ItemDataRole.UserRole, 0)
            item.setCheckState(0, Qt.CheckState.Checked)
            window.tree.addTopLevelItem(item)
            window.tree.setCurrentItem(item)
            window.resize(1120, 710)
            window.show()
            app.processEvents()
            assert len(window.selection()) == 1 and window.preview.toPlainText()
            assert not window.grab().isNull()
            window.close()
            results["checks"].append("Qt widgets, fonts and image plugins")

            async def check_models():
                for provider in PROVIDERS.values():
                    async with generator(provider, "synthetic-key-for-offline-tests") as generate:
                        assert callable(generate)
                calls = []

                async def summarize(system, prompt, limit):
                    calls.append(prompt)
                    return "## 核心需求\n保留关键代码与当前决定。"

                summary = await compact(summarize, PROVIDERS["DeepSeek"], sessions[0].text, lambda message: None)
                assert len(calls) > 1
                return summary

            summary = asyncio.run(check_models())
            results["checks"].append("all provider SDK clients and chunked summarization")
            for harness, filename in MEMORY_FILES.items():
                folder = write_bundle(new_batch(root), 1, sessions[0].title, summary, harness)
                assert (folder / filename).is_file() and (folder / "CONTEXT.md").is_file()
            results["checks"].append("four harness exports")
            database = root / "keys.db"
            vault.save(database, "demo", "synthetic-key", "synthetic-password")
            assert vault.load(database, "demo", "synthetic-password") == "synthetic-key"
            try:
                vault.load(database, "demo", "wrong-password")
            except InvalidTag:
                pass
            else:
                raise AssertionError("The vault accepted an incorrect password")
            results["checks"].append("SQLite, PBKDF2 and AES-GCM")
        results["ok"] = True
    except Exception:
        results["ok"] = False
        results["error"] = traceback.format_exc()
    report.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0 if results["ok"] else 1
