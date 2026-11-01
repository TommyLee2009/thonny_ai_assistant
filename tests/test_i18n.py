import ast
import importlib
import unittest
from pathlib import Path
from unittest.mock import patch

from thonnycontrib.thonny_ai_assistant import i18n


PACKAGE_DIR = Path(__file__).resolve().parents[1] / "thonnycontrib" / "thonny_ai_assistant"


class WorkbenchStub:
    def __init__(self, language, options=None):
        self.language = language
        self.options = options or {}
        self.views = []
        self.commands = []

    def get_option(self, name):
        if name == "general.language":
            return self.language
        return self.options.get(name)

    def add_view(
        self,
        view_class,
        label,
        location,
        visible_by_default=False,
        default_position_key=None,
    ):
        self.views.append(
            (
                view_class.__name__,
                label,
                location,
                default_position_key,
            )
        )

    def add_command(self, **kwargs):
        self.commands.append(kwargs)


class LocalizationTests(unittest.TestCase):
    def tearDown(self):
        i18n.reset_language_cache()

    def test_chinese_and_english_translation(self):
        with patch.object(i18n, "get_workbench", return_value=WorkbenchStub("zh_CN")):
            i18n.reset_language_cache()
            self.assertEqual(i18n.tr("Send"), "发送")
            self.assertEqual(i18n.tr("Loaded {count} models", count=3), "已加载 3 个模型")

        with patch.object(i18n, "get_workbench", return_value=WorkbenchStub("en_US")):
            i18n.reset_language_cache()
            self.assertEqual(i18n.tr("Send"), "Send")
            self.assertEqual(i18n.tr("Loaded {count} models", count=3), "Loaded 3 models")

    def test_other_languages_fall_back_to_english(self):
        with patch.object(i18n, "get_workbench", return_value=WorkbenchStub("fr_FR")):
            i18n.reset_language_cache()
            self.assertEqual(i18n.get_ui_language(), "en")
            self.assertEqual(i18n.tr("Settings"), "Settings")

    def test_all_translation_keys_are_complete(self):
        used_keys = set()
        for filename in ("__init__.py", "thonny_ai_assistant_tool.py"):
            tree = ast.parse(
                (PACKAGE_DIR / filename).read_text(encoding="utf-8")
            )
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                if not isinstance(node.func, ast.Name) or node.func.id != "tr":
                    continue
                if (
                    node.args
                    and isinstance(node.args[0], ast.Constant)
                    and isinstance(node.args[0].value, str)
                ):
                    used_keys.add(node.args[0].value)

        self.assertEqual(used_keys, set(i18n._ZH_CN))


class PluginRegistrationTests(unittest.TestCase):
    def tearDown(self):
        i18n.reset_language_cache()

    def _load_labels(self, language):
        plugin = importlib.import_module("thonnycontrib.thonny_ai_assistant")
        workbench = WorkbenchStub(language)
        with patch.object(i18n, "get_workbench", return_value=workbench):
            with patch.object(plugin, "get_workbench", return_value=workbench):
                i18n.reset_language_cache()
                plugin.load_plugin()
        return workbench

    def test_chinese_registration_labels(self):
        workbench = self._load_labels("zh_CN")
        self.assertEqual(workbench.views[0][1], "AI助手")
        command = next(
            item
            for item in workbench.commands
            if item["command_id"] == "thonny_ai_assistant"
        )
        self.assertEqual(command["command_label"], "打开 AI助手")
        self.assertEqual(command["caption"], "AI助手")

    def test_english_registration_labels(self):
        workbench = self._load_labels("en_US")
        self.assertEqual(workbench.views[0][1], "AI Assistant")
        command = next(
            item
            for item in workbench.commands
            if item["command_id"] == "thonny_ai_assistant"
        )
        self.assertEqual(command["command_label"], "Open AI Assistant")
        self.assertEqual(command["caption"], "AI Assistant")


if __name__ == "__main__":
    unittest.main()
