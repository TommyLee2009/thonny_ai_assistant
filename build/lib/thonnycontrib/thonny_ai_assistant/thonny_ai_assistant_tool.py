import os
import sys
import queue
import copy
import re
import tkinter as tk
from tkinter import ttk, messagebox
import threading
import json
import uuid
from pathlib import Path
from urllib.parse import urlparse

from thonnycontrib.thonny_ai_assistant.i18n import get_ui_language, tr

_OPENAI_IMPORT_ERROR = None

try:
    from openai import OpenAI
    OPENAI_SDK_AVAILABLE = True
except Exception as exc:
    OpenAI = None
    OPENAI_SDK_AVAILABLE = False
    _OPENAI_IMPORT_ERROR = exc


def _ensure_openai_sdk_available():
    """Retry the SDK import so a stale startup failure can recover."""
    global OpenAI, OPENAI_SDK_AVAILABLE, _OPENAI_IMPORT_ERROR

    if OPENAI_SDK_AVAILABLE:
        return True

    try:
        from openai import OpenAI as OpenAIClient
    except Exception as exc:
        _OPENAI_IMPORT_ERROR = exc
        return False

    OpenAI = OpenAIClient
    OPENAI_SDK_AVAILABLE = True
    _OPENAI_IMPORT_ERROR = None
    return True


def _show_openai_sdk_error():
    details = [
        tr(
            "OpenAI-compatible SDK is required: "
            "pip install \"openai>=1.75.0\""
        ),
        "",
        tr("Current interpreter: {executable}", executable=sys.executable),
    ]
    if _OPENAI_IMPORT_ERROR is not None:
        details.extend(
            [
                "",
                tr(
                    "Import error: {error_type}: {error}",
                    error_type=type(_OPENAI_IMPORT_ERROR).__name__,
                    error=_OPENAI_IMPORT_ERROR,
                ),
            ]
        )
    messagebox.showerror(tr("Missing dependency"), "\n".join(details))

# Import only the necessary functions
from thonny import get_workbench

DEEPSEEK_API_BASE = "https://api.deepseek.com"
CONFIG_VERSION = 4
MIN_OUTPUT_TOKENS = 256
MAX_OUTPUT_TOKENS = 65536
OUTPUT_TOKEN_STEP = 256
DEFAULT_MAX_TOKENS = 8192

# Verified against DeepSeek's /models endpoint on 2026-10-28. These entries
# keep the selector usable if automatic model discovery is temporarily offline.
FALLBACK_MODELS = (
    {
        "id": "deepseek-flash",
        "name": "DeepSeek-V4.1-Flash",
        "context_window": 1048576,
        "max_output_tokens": 393216,
    },
    {
        "id": "deepseek-v4-pro",
        "name": "DeepSeek-V4-Pro",
        "context_window": 1048576,
        "max_output_tokens": 393216,
    },
)
DEFAULT_MODEL_ID = "deepseek-flash"

# Configuration file paths
CONFIG_DIR = os.path.join(
    str(Path.home()), ".thonny", "thonny_ai_assistant_config"
)
CONFIG_FILE = os.path.join(CONFIG_DIR, "config.json")
PREVIOUS_CONFIG_FILE = os.path.join(
    str(Path.home()), ".thonny", "ai_assistant_config", "config.json"
)
LEGACY_CONFIG_FILE = os.path.join(
    str(Path.home()), ".thonny", "deepseek_config", "config.json"
)

DEFAULT_PROVIDER = {
    "id": "deepseek",
    "name": "DeepSeek",
    "api_base": DEEPSEEK_API_BASE,
    "api_key": "",
    "model": DEFAULT_MODEL_ID,
    "models": [model.copy() for model in FALLBACK_MODELS],
}

DEFAULT_CONFIG = {
    "config_version": CONFIG_VERSION,
    "provider_id": DEFAULT_PROVIDER["id"],
    "providers": [copy.deepcopy(DEFAULT_PROVIDER)],
    "system_prompt": "",
    "temperature": 0.7,
    "max_tokens": DEFAULT_MAX_TOKENS,
    "enable_thinking": False,
    "chat_history": []
}

# Ensure config directory exists
os.makedirs(CONFIG_DIR, exist_ok=True)

# Global variable for external access to the AI assistant view.
_global_ai_chat_view = None


def _read_model_value(model, key, default=None):
    """Read a model field from an API object or a plain dictionary."""
    if isinstance(model, dict):
        return model.get(key, default)
    return getattr(model, key, default)


def normalize_models(models):
    """Normalize API model objects and remove duplicate IDs."""
    normalized = []
    seen_ids = set()
    for model in models or []:
        model_id = str(_read_model_value(model, "id", "") or "").strip()
        if not model_id or model_id in seen_ids:
            continue

        model_name = str(
            _read_model_value(model, "name", model_id) or model_id
        ).strip()
        item = {
            "id": model_id,
            "name": model_name,
        }
        for field in ("context_window", "max_output_tokens"):
            value = _read_model_value(model, field)
            if value is not None:
                item[field] = value
        normalized.append(item)
        seen_ids.add(model_id)
    return normalized


def format_model_label(model):
    """Show the concrete model name without the API model ID."""
    model_id = model["id"]
    model_name = model.get("name") or model_id
    return model_name


def normalize_api_base(api_base):
    """Normalize a provider's OpenAI-compatible base URL."""
    return str(api_base or "").strip().rstrip("/")


def is_valid_api_base(api_base):
    """Return whether the provider URL is an HTTP(S) base URL."""
    parsed = urlparse(api_base)
    return parsed.scheme in ("http", "https") and bool(parsed.netloc)


def is_aliyun_bailian_api(api_base):
    """Return whether the URL is an Alibaba Cloud Model Studio endpoint."""
    hostname = (urlparse(api_base).hostname or "").casefold()
    return hostname.endswith(".aliyuncs.com")


def is_direct_deepseek_api(api_base):
    """Return whether the URL is DeepSeek's official API endpoint."""
    hostname = (urlparse(api_base).hostname or "").casefold()
    return hostname == "api.deepseek.com"


def configure_thinking_in_request(request_args, provider, enabled):
    """Configure the provider-specific thinking switch when supported."""
    api_base = provider.get("api_base", "")
    if is_aliyun_bailian_api(api_base):
        extra_body = dict(request_args.get("extra_body") or {})
        extra_body["enable_thinking"] = bool(enabled)
        request_args["extra_body"] = extra_body
        return True
    if is_direct_deepseek_api(api_base) and not enabled:
        request_args["reasoning_effort"] = "none"
        return True
    return False


def mask_api_key(api_key):
    """Return a non-sensitive display value for a saved API key."""
    if not api_key:
        return tr("Not set")
    if len(api_key) <= 10:
        return "*" * len(api_key)
    return f"{api_key[:5]}{'*' * (len(api_key) - 10)}{api_key[-5:]}"


def normalize_output_tokens(value):
    """Clamp a saved output-token value to the supported range."""
    try:
        tokens = int(value)
    except (TypeError, ValueError):
        tokens = DEFAULT_MAX_TOKENS
    return max(MIN_OUTPUT_TOKENS, min(MAX_OUTPUT_TOKENS, tokens))


def snap_output_tokens(value):
    """Round a slider value to the nearest supported token step."""
    try:
        raw_value = float(value)
    except (TypeError, ValueError):
        raw_value = float(DEFAULT_MAX_TOKENS)
    step = max(1, OUTPUT_TOKEN_STEP)
    return normalize_output_tokens(round(raw_value / step) * step)


def make_provider_id():
    """Create a stable unique ID for a new provider."""
    return f"provider-{uuid.uuid4().hex[:12]}"


def normalize_providers(providers):
    """Normalize provider dictionaries and enforce unique names and IDs."""
    normalized = []
    seen_ids = set()
    seen_names = set()
    for index, provider in enumerate(providers or []):
        if not isinstance(provider, dict):
            continue

        provider_id = str(provider.get("id") or "").strip()
        if not provider_id or provider_id in seen_ids:
            provider_id = make_provider_id()

        name = str(provider.get("name") or "").strip()
        if not name:
            name = tr("Provider {index}", index=index + 1)
        base_name = name
        suffix = 2
        while name.casefold() in seen_names:
            name = f"{base_name} ({suffix})"
            suffix += 1

        api_base = normalize_api_base(provider.get("api_base"))
        if not api_base:
            api_base = DEEPSEEK_API_BASE

        models = normalize_models(provider.get("models"))
        model_id = str(provider.get("model") or "").strip()
        available_model_ids = {model["id"] for model in models}
        if model_id not in available_model_ids:
            model_id = models[0]["id"] if models else ""

        normalized.append({
            "id": provider_id,
            "name": name,
            "api_base": api_base,
            "api_key": str(provider.get("api_key") or "").strip(),
            "model": model_id,
            "models": models,
        })
        seen_ids.add(provider_id)
        seen_names.add(name.casefold())
    return normalized


def get_provider(config, provider_id=None):
    """Return a provider from the normalized configuration."""
    providers = config.get("providers", [])
    target_id = provider_id or config.get("provider_id")
    for provider in providers:
        if provider.get("id") == target_id:
            return provider
    return providers[0] if providers else None


def get_editor_notebook():
    """Alternative method to get editor notebook"""
    wb = get_workbench()
    try:
        # Method for Thonny 4.0+
        editor_notebook = wb.get_editor_notebook()
        return editor_notebook
    except Exception:
        try:
            # Look for other possible methods to find editor notebook
            for attr_name in dir(wb):
                if 'editor' in attr_name.lower():
                    editor_obj = getattr(wb, attr_name)
                    if hasattr(editor_obj, 'get_current_editor'):
                        return editor_obj
        except Exception:
            pass
        
        print("Unable to get editor notebook, some features may not work properly")
        return None

def get_current_editor():
    """Generic method to get the current editor"""
    try:
        editor_notebook = get_editor_notebook()
        if editor_notebook:
            return editor_notebook.get_current_editor()
    except Exception:
        pass
    
    # If the above method fails, try getting it directly from the workbench
    try:
        wb = get_workbench()
        if hasattr(wb, 'get_current_editor'):
            return wb.get_current_editor()
    except Exception:
        pass
    
    return None

def get_editor_text(editor):
    """Generic method to get text from editor"""
    if not editor:
        return None
    
    try:
        # Try multiple possible methods to get editor text
        methods = [
            lambda: editor.get_text_widget().get("1.0", tk.END),
            lambda: editor.get_text_content(),
            lambda: editor.get("1.0", tk.END),
            lambda: editor.text.get("1.0", tk.END),
            lambda: editor.get_code_view().get("1.0", tk.END),
            lambda: editor.get_content()
        ]
        
        for method in methods:
            try:
                code = method()
                if code:
                    return code
            except (AttributeError, TypeError):
                continue
    except Exception as e:
        print(f"Error getting editor text: {e}")
    
    return None


def get_editor_selection_text(editor):
    """Return selected editor text, or None when there is no selection."""
    if not editor:
        return None

    widgets = []
    for getter_name in ("get_text_widget", "get_code_view"):
        try:
            getter = getattr(editor, getter_name)
            widget = getter()
            if widget is not None:
                widgets.append(widget)
        except (AttributeError, TypeError, tk.TclError):
            continue

    try:
        widgets.append(editor.text)
    except AttributeError:
        pass

    if hasattr(editor, "get"):
        widgets.append(editor)

    for widget in widgets:
        try:
            ranges = widget.tag_ranges(tk.SEL)
            if len(ranges) >= 2:
                selected = widget.get(ranges[0], ranges[1])
                if selected and selected.strip():
                    return selected
        except (AttributeError, TypeError, tk.TclError):
            pass

        try:
            selected = widget.get("sel.first", "sel.last")
            if selected and selected.strip():
                return selected
        except (AttributeError, TypeError, tk.TclError):
            pass

    for method_name in ("get_selected_text", "get_selection_text"):
        try:
            selected = getattr(editor, method_name)()
            if selected and selected.strip():
                return selected
        except (AttributeError, TypeError, tk.TclError):
            continue

    return None


def get_editor_text_widget(editor):
    """Return the Tk text widget behind a Thonny editor."""
    if not editor:
        return None

    for getter_name in ("get_text_widget", "get_code_view"):
        try:
            widget = getattr(editor, getter_name)()
            if widget is not None and hasattr(widget, "insert"):
                return widget
        except (AttributeError, TypeError, tk.TclError):
            continue

    try:
        widget = editor.text
        if widget is not None and hasattr(widget, "insert"):
            return widget
    except AttributeError:
        pass

    if hasattr(editor, "insert"):
        return editor
    return None


def get_widget_selection_text(widget):
    """Return selected text from a Tk Text widget."""
    try:
        ranges = widget.tag_ranges(tk.SEL)
        if len(ranges) >= 2:
            selected = widget.get(ranges[0], ranges[1])
            if selected:
                return selected
    except (AttributeError, TypeError, tk.TclError):
        pass

    try:
        selected = widget.get("sel.first", "sel.last")
        if selected:
            return selected
    except (AttributeError, TypeError, tk.TclError):
        pass
    return None


def insert_text_at_editor_cursor(editor, text):
    """Insert text at the current Thonny editor cursor."""
    widget = get_editor_text_widget(editor)
    if widget is None:
        return False

    try:
        widget.insert(tk.INSERT, text)
        widget.focus_set()
        widget.see(tk.INSERT)
        return True
    except (AttributeError, TypeError, tk.TclError):
        return False


def get_current_interpreter_context():
    """Describe the interpreter selected in Thonny's current backend."""
    wb = None
    try:
        wb = get_workbench()
        backend_name = str(
            wb.get_option("run.backend_name") or ""
        ).strip()
    except Exception:
        backend_name = ""

    description = backend_name or tr("Unknown")
    executable = ""
    if wb is not None:
        try:
            backends = wb.get_backends()
            backend_spec = backends.get(backend_name)
            if backend_spec is not None:
                description = str(
                    getattr(backend_spec, "description", "")
                    or backend_name
                    or tr("Unknown")
                ).strip()
        except Exception:
            pass

        if backend_name:
            try:
                executable = str(
                    wb.get_option(f"{backend_name}.executable") or ""
                ).strip()
            except Exception:
                pass

    lines = [
        tr(
            "Current interpreter environment: {description}",
            description=description,
        ),
        tr(
            "Thonny interpreter type: {backend_name}",
            backend_name=backend_name or tr("Unknown"),
        ),
    ]
    if executable:
        lines.append(
            tr("Interpreter executable: {executable}", executable=executable)
        )
    lines.append(
        tr(
            "Use this interpreter environment to determine the available "
            "syntax, standard library, third-party packages, and hardware "
            "APIs. Do not assume the user is running desktop CPython."
        )
    )
    return "\n".join(lines)


def compose_system_prompt(custom_prompt, interpreter_context):
    """Combine the custom role prompt with automatic interpreter context."""
    parts = []
    custom_text = str(custom_prompt or "").strip()
    context_text = str(interpreter_context or "").strip()
    if custom_text:
        parts.append(custom_text)
    if context_text:
        parts.append(context_text)
    return "\n\n".join(parts)


def load_config():
    """Load provider configuration and migrate the legacy DeepSeek format."""
    config = copy.deepcopy(DEFAULT_CONFIG)
    if os.path.exists(CONFIG_FILE):
        source_file = CONFIG_FILE
    elif os.path.exists(PREVIOUS_CONFIG_FILE):
        source_file = PREVIOUS_CONFIG_FILE
    else:
        source_file = LEGACY_CONFIG_FILE
    saved_config = {}
    if os.path.exists(source_file):
        try:
            with open(source_file, "r", encoding="utf-8") as f:
                saved_config = json.load(f)
            if isinstance(saved_config, dict):
                config.update(saved_config)
        except Exception:
            saved_config = {}

    try:
        saved_version = int(saved_config.get("config_version", 0))
    except (TypeError, ValueError):
        saved_version = 0
    if saved_version < CONFIG_VERSION:
        try:
            saved_max_tokens = int(config.get("max_tokens"))
        except (TypeError, ValueError):
            saved_max_tokens = 0
        if saved_max_tokens <= 2048:
            config["max_tokens"] = DEFAULT_MAX_TOKENS

    if saved_config and "providers" not in saved_config:
        providers = []
    else:
        providers = normalize_providers(config.get("providers"))
    if not providers:
        api_base = normalize_api_base(
            saved_config.get("api_base") or DEEPSEEK_API_BASE
        )
        legacy_models = normalize_models(
            saved_config.get("available_models")
        )
        if not legacy_models and "deepseek" in api_base.lower():
            legacy_models = [model.copy() for model in FALLBACK_MODELS]
        provider_name = str(
            saved_config.get("provider_name")
            or (
                "DeepSeek"
                if "deepseek" in api_base.lower()
                else tr("Default provider")
            )
        ).strip()
        providers = normalize_providers([{
            "id": saved_config.get("provider_id")
            or saved_config.get("provider")
            or "default",
            "name": provider_name,
            "api_base": api_base,
            "api_key": saved_config.get("api_key", ""),
            "model": saved_config.get("model", ""),
            "models": legacy_models,
        }])

    if not providers:
        providers = [copy.deepcopy(DEFAULT_PROVIDER)]
    config["providers"] = providers
    provider_ids = {provider["id"] for provider in providers}
    if config.get("provider_id") not in provider_ids:
        config["provider_id"] = providers[0]["id"]
    if not isinstance(config.get("chat_history"), list):
        config["chat_history"] = []
    config["system_prompt"] = str(config.get("system_prompt") or "").strip()
    config["enable_thinking"] = bool(config.get("enable_thinking", False))
    config["config_version"] = CONFIG_VERSION
    return config


def save_config(config):
    """Save provider configuration."""
    providers = normalize_providers(config.get("providers"))
    if not providers:
        providers = [copy.deepcopy(DEFAULT_PROVIDER)]
    config["providers"] = providers
    provider_ids = {provider["id"] for provider in providers}
    if config.get("provider_id") not in provider_ids:
        config["provider_id"] = providers[0]["id"]
    config["system_prompt"] = str(config.get("system_prompt") or "").strip()
    config["config_version"] = CONFIG_VERSION
    config.pop("provider", None)
    config.pop("api_base", None)
    config.pop("api_key", None)
    config.pop("model", None)
    config.pop("available_models", None)
    os.makedirs(os.path.dirname(CONFIG_FILE), exist_ok=True)
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)
    try:
        os.chmod(CONFIG_FILE, 0o600)
    except OSError:
        # Windows may ignore POSIX permissions; this is best-effort only.
        pass

class ProviderSettingsDialog(tk.Toplevel):
    """Dialog for adding and editing OpenAI-compatible model providers."""

    def __init__(self, master, config, on_saved=None):
        super().__init__(master)
        self.title(tr("AI Assistant Settings"))
        self.geometry("700x640")
        self.minsize(620, 560)
        self.resizable(True, True)
        self.transient(master)
        self.grab_set()

        self.config = copy.deepcopy(config)
        self.on_saved = on_saved
        self.current_provider_id = config.get("provider_id")

        self.provider_name_var = tk.StringVar()
        self.api_base_var = tk.StringVar()
        self.api_key_var = tk.StringVar()
        self.key_hint_var = tk.StringVar()
        self.temp_var = tk.DoubleVar(
            value=float(
                self.config.get(
                    "temperature",
                    DEFAULT_CONFIG["temperature"],
                )
            )
        )
        initial_max_tokens = normalize_output_tokens(
            self.config.get("max_tokens", DEFAULT_CONFIG["max_tokens"])
        )
        self.max_tokens_var = tk.IntVar(value=initial_max_tokens)
        self.max_tokens_scale_var = tk.DoubleVar(value=initial_max_tokens)
        self.output_tokens_value_var = tk.StringVar(
            value=f"{initial_max_tokens:,}"
        )

        form = ttk.Frame(self, padding=12)
        form.pack(fill=tk.BOTH, expand=True)
        form.columnconfigure(1, weight=1)
        form.rowconfigure(6, weight=1)

        ttk.Label(form, text=tr("Provider name:")).grid(
            row=0, column=0, sticky="w", pady=5
        )
        self.provider_menu = ttk.Combobox(
            form,
            textvariable=self.provider_name_var,
            values=[provider["name"] for provider in self.config["providers"]],
            state="normal"
        )
        self.provider_menu.grid(row=0, column=1, sticky="ew", pady=5)
        self.provider_menu.bind("<<ComboboxSelected>>", self._on_provider_selected)

        ttk.Label(form, text=tr("API base URL:")).grid(
            row=1, column=0, sticky="w", pady=5
        )
        ttk.Entry(form, textvariable=self.api_base_var).grid(
            row=1, column=1, sticky="ew", pady=5
        )

        ttk.Label(form, text=tr("API Key:")).grid(
            row=2, column=0, sticky="w", pady=5
        )
        ttk.Entry(
            form,
            textvariable=self.api_key_var,
            show="*"
        ).grid(row=2, column=1, sticky="ew", pady=5)

        ttk.Label(
            form,
            textvariable=self.key_hint_var,
            foreground="gray"
        ).grid(row=3, column=1, sticky="w", pady=(0, 8))

        ttk.Label(
            form,
            text=tr(
                "Supports OpenAI-compatible /models and "
                "/chat/completions endpoints."
            ),
            foreground="gray"
        ).grid(row=4, column=0, columnspan=2, sticky="w", pady=(0, 8))

        generation_frame = ttk.LabelFrame(
            form,
            text=tr("Generation settings"),
            padding=(8, 6),
        )
        generation_frame.grid(
            row=5,
            column=0,
            columnspan=2,
            sticky="ew",
            pady=(0, 8),
        )
        generation_frame.columnconfigure(1, weight=1)

        ttk.Label(
            generation_frame,
            text=tr("Temperature:"),
        ).grid(row=0, column=0, sticky="w", padx=(0, 6))
        ttk.Scale(
            generation_frame,
            from_=0,
            to=2,
            orient=tk.HORIZONTAL,
            variable=self.temp_var,
            length=220,
        ).grid(row=0, column=1, sticky="ew", padx=(0, 6))
        self.temp_value_label = ttk.Label(
            generation_frame,
            text=f"{self.temp_var.get():.2f}",
            width=5,
            anchor="e",
        )
        self.temp_value_label.grid(row=0, column=2, sticky="e")
        self.temp_var.trace_add(
            "write",
            lambda *_: self.temp_value_label.configure(
                text=f"{self.temp_var.get():.2f}"
            ),
        )

        ttk.Label(
            generation_frame,
            text=tr("Output tokens:"),
        ).grid(row=1, column=0, sticky="w", padx=(0, 6), pady=(6, 0))
        ttk.Scale(
            generation_frame,
            from_=MIN_OUTPUT_TOKENS,
            to=MAX_OUTPUT_TOKENS,
            orient=tk.HORIZONTAL,
            variable=self.max_tokens_scale_var,
            command=self._on_output_tokens_changed,
            length=220,
        ).grid(
            row=1,
            column=1,
            sticky="ew",
            padx=(0, 6),
            pady=(6, 0),
        )
        ttk.Label(
            generation_frame,
            textvariable=self.output_tokens_value_var,
            width=8,
            anchor="e",
        ).grid(row=1, column=2, sticky="e", pady=(6, 0))

        ttk.Label(form, text=tr("System prompt:")).grid(
            row=6, column=0, sticky="nw", pady=(2, 4)
        )
        prompt_frame = ttk.Frame(form)
        prompt_frame.grid(row=6, column=1, sticky="nsew", pady=(2, 4))
        prompt_frame.columnconfigure(0, weight=1)
        prompt_frame.rowconfigure(0, weight=1)

        self.system_prompt_text = tk.Text(
            prompt_frame,
            wrap=tk.WORD,
            height=9,
            undo=True
        )
        self.system_prompt_text.grid(
            row=0, column=0, sticky="nsew"
        )
        self.system_prompt_scrollbar = ttk.Scrollbar(
            prompt_frame,
            orient=tk.VERTICAL,
            command=self.system_prompt_text.yview
        )
        self.system_prompt_scrollbar.grid(
            row=0, column=1, sticky="ns"
        )
        self.system_prompt_text.configure(
            yscrollcommand=self.system_prompt_scrollbar.set
        )
        self.system_prompt_text.insert(
            "1.0",
            str(self.config.get("system_prompt") or "")
        )
        self._apply_system_prompt_theme()

        ttk.Label(
            form,
            text=tr(
                "Define the AI role, response structure, and quality "
                "requirements. Thonny compiler/interpreter information is "
                "still added automatically."
            ),
            foreground="gray"
        ).grid(
            row=7,
            column=1,
            sticky="w",
            pady=(0, 8)
        )

        button_row = ttk.Frame(form)
        button_row.grid(
            row=8,
            column=0,
            columnspan=2,
            sticky="ew",
            pady=(6, 0)
        )
        ttk.Button(
            button_row, text=tr("Add provider"), command=self._new_provider
        ).pack(side=tk.LEFT)
        ttk.Button(
            button_row, text=tr("Delete current"), command=self._delete_provider
        ).pack(side=tk.LEFT, padx=(6, 0))
        ttk.Button(
            button_row, text=tr("Cancel"), command=self.destroy
        ).pack(side=tk.RIGHT)
        ttk.Button(
            button_row,
            text=tr("Save and fetch models"),
            command=self._save_provider
        ).pack(side=tk.RIGHT, padx=(0, 6))

        current_provider = get_provider(self.config)
        if current_provider:
            self._load_provider(current_provider)
        self.bind(
            "<<ThemeChanged>>",
            lambda event: self.after_idle(self._apply_system_prompt_theme),
            add="+"
        )
        self.protocol("WM_DELETE_WINDOW", self.destroy)

    def _apply_system_prompt_theme(self):
        """Match the prompt editor to Thonny's active Text style."""
        style = ttk.Style(self)
        self.system_prompt_text.configure(
            background=style.lookup("Text", "background"),
            foreground=style.lookup("Text", "foreground"),
            insertbackground=style.lookup("Text", "foreground"),
            selectbackground=style.lookup(".", "selectbackground"),
            selectforeground=style.lookup(".", "selectforeground")
        )

    def _on_output_tokens_changed(self, value):
        """Snap the token slider to the configured step size."""
        tokens = snap_output_tokens(value)
        self.max_tokens_var.set(tokens)
        self.output_tokens_value_var.set(f"{tokens:,}")

    def _store_generation_settings(self):
        """Copy temperature and token limits into the dialog config."""
        temperature = max(0.0, min(2.0, float(self.temp_var.get())))
        tokens = snap_output_tokens(self.max_tokens_scale_var.get())
        self.max_tokens_var.set(tokens)
        self.output_tokens_value_var.set(f"{tokens:,}")
        self.config["temperature"] = round(temperature, 2)
        self.config["max_tokens"] = tokens

    def _store_system_prompt(self):
        """Copy the current prompt editor content into the dialog config."""
        self.config["system_prompt"] = (
            self.system_prompt_text.get("1.0", tk.END).strip()
        )

    def _load_provider(self, provider):
        self.current_provider_id = provider.get("id")
        self.provider_name_var.set(provider.get("name", ""))
        self.api_base_var.set(provider.get("api_base", ""))
        self.api_key_var.set("")
        self.key_hint_var.set(
            tr(
                "Saved key: {key}; leave blank to keep it",
                key=mask_api_key(provider.get("api_key", "")),
            )
        )

    def _on_provider_selected(self, event=None):
        selected_name = self.provider_name_var.get().strip().casefold()
        for provider in self.config["providers"]:
            if provider["name"].casefold() == selected_name:
                self._load_provider(provider)
                return

    def _new_provider(self):
        self.current_provider_id = None
        self.provider_name_var.set("")
        self.api_base_var.set("")
        self.api_key_var.set("")
        self.key_hint_var.set(tr("API Key is required for a new provider."))
        self.provider_menu.focus_set()

    def _delete_provider(self):
        selected_name = self.provider_name_var.get().strip().casefold()
        provider = next(
            (
                item for item in self.config["providers"]
                if item["name"].casefold() == selected_name
            ),
            None
        )
        if provider is None:
            messagebox.showwarning(
                tr("Provider not found"),
                tr("Select a provider to delete first."),
                parent=self
            )
            return
        if not messagebox.askyesno(
            tr("Delete provider"),
            tr(
                "Delete “{provider}” and its local configuration?",
                provider=provider["name"],
            ),
            parent=self
        ):
            return

        self.config["providers"] = [
            item for item in self.config["providers"]
            if item["id"] != provider["id"]
        ]
        if not self.config["providers"]:
            self.config["providers"] = [copy.deepcopy(DEFAULT_PROVIDER)]
        self.config["provider_id"] = self.config["providers"][0]["id"]
        self._store_system_prompt()
        self._store_generation_settings()
        save_config(self.config)
        if self.on_saved:
            self.on_saved(copy.deepcopy(self.config), self.config["provider_id"])
        self.destroy()

    def _save_provider(self):
        name = self.provider_name_var.get().strip()
        api_base = normalize_api_base(self.api_base_var.get())
        entered_key = self.api_key_var.get().strip()

        if not name:
            messagebox.showwarning(
                tr("Missing name"),
                tr("Enter a provider name."),
                parent=self,
            )
            return
        if not is_valid_api_base(api_base):
            messagebox.showwarning(
                tr("Invalid API base URL"),
                tr(
                    "Enter an API base URL beginning with http:// or "
                    "https://."
                ),
                parent=self
            )
            return

        existing = next(
            (
                item for item in self.config["providers"]
                if item["id"] == self.current_provider_id
            ),
            None
        )
        if existing is None:
            existing = next(
                (
                    item for item in self.config["providers"]
                    if item["name"].casefold() == name.casefold()
                ),
                None
            )
        name_conflict = next(
            (
                item for item in self.config["providers"]
                if item["name"].casefold() == name.casefold()
                and item["id"] != (existing or {}).get("id")
            ),
            None
        )
        if name_conflict is not None:
            messagebox.showwarning(
                tr("Duplicate provider name"),
                tr("Use a different provider name."),
                parent=self
            )
            return
        api_key = entered_key or (existing or {}).get("api_key", "")
        if not api_key:
            messagebox.showwarning(
                tr("Missing API Key"),
                tr("Enter the API Key for this provider."),
                parent=self
            )
            return

        if existing:
            provider_id = existing["id"]
            provider = existing
        else:
            provider_id = make_provider_id()
            provider = {
                "id": provider_id,
                "name": name,
                "api_base": api_base,
                "api_key": api_key,
                "model": "",
                "models": [],
            }
            self.config["providers"].append(provider)

        provider["name"] = name
        provider["api_base"] = api_base
        provider["api_key"] = api_key
        self.config["providers"] = normalize_providers(
            self.config["providers"]
        )
        self.config["provider_id"] = provider_id
        self._store_system_prompt()
        self._store_generation_settings()
        save_config(self.config)
        if self.on_saved:
            self.on_saved(copy.deepcopy(self.config), provider_id)
        self.destroy()


class AIChatView(ttk.Frame):
    """Multi-provider AI chat side panel."""

    @classmethod
    def show_api_key_dialog(cls):
        """Open the provider settings dialog from the Tools menu."""
        if _global_ai_chat_view is not None:
            _global_ai_chat_view._show_settings()
            return
        master = tk._default_root
        if master is None:
            return
        ProviderSettingsDialog(master, load_config())
    
    def __init__(self, master):
        super().__init__(master)
        
        global _global_ai_chat_view
        _global_ai_chat_view = self
        
        self.config = load_config()
        self.messages = self.config.get("chat_history", [])
        self._api_results = queue.Queue()
        self._model_results = queue.Queue()
        self._request_pending = False
        self._models_loading = False
        self._streaming_started = False
        self._streaming_text = ""
        self._streaming_start_mark = "assistant_stream_start"

        self._prepare_provider_choices(
            self.config,
            self.config.get("provider_id")
        )
        current_provider = self._current_provider()
        self.provider_var = tk.StringVar(
            value=current_provider["name"]
        )

        self.model_id_by_label = {}
        self.label_by_model_id = {}
        selected_model_id = self._prepare_model_choices(
            current_provider.get("models", []),
            current_provider.get("model", ""),
            use_fallback=False
        )
        self.model_var = tk.StringVar(
            value=(
                self.label_by_model_id[selected_model_id]
                if selected_model_id
                else tr("Fetch a model first")
            )
        )
        self.model_status_var = tk.StringVar(
            value=tr(
                "Loaded {count} models",
                count=len(self.available_models),
            )
        )
        self.temp_var = tk.DoubleVar(
            value=self.config.get(
                "temperature",
                DEFAULT_CONFIG["temperature"],
            )
        )
        initial_max_tokens = normalize_output_tokens(
            self.config.get("max_tokens", DEFAULT_CONFIG["max_tokens"])
        )
        self.max_tokens_var = tk.IntVar(value=initial_max_tokens)
        self.thinking_var = tk.BooleanVar(
            value=bool(self.config.get("enable_thinking", False))
        )
        
        self._init_ui()
        self._load_chat_history()
        self.after(100, self._poll_api_results)
        self.after(100, self._poll_model_results)
        if current_provider.get("api_key"):
            self.after(250, self.refresh_models)
        
    def _init_ui(self):
        """Initialize user interface"""
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)
        
        # Top control area
        control_frame = ttk.Frame(self)
        control_frame.grid(row=0, column=0, sticky="ew", padx=5, pady=5)

        provider_row = ttk.Frame(control_frame)
        provider_row.pack(fill=tk.X)
        provider_row.columnconfigure(1, weight=1)

        self.provider_label = ttk.Label(
            provider_row,
            text=tr("Provider:"),
            font=("TkDefaultFont", 10),
            width=8,
            anchor="w"
        )
        self.provider_label.grid(
            row=0, column=0, sticky="w", padx=(0, 5)
        )
        self.provider_menu = ttk.Combobox(
            provider_row,
            textvariable=self.provider_var,
            values=list(self._provider_id_by_label.keys()),
            width=24,
            state="readonly"
        )
        self.provider_menu.grid(row=0, column=1, sticky="ew", padx=(0, 5))
        self.provider_menu.bind(
            "<<ComboboxSelected>>", self._on_provider_changed
        )

        settings_button = ttk.Button(
            provider_row, text="⚙️", width=3, command=self._show_settings
        )
        settings_button.grid(row=0, column=2, padx=(0, 2))

        clear_button = ttk.Button(
            provider_row, text="🗑️", width=3, command=self._clear_chat
        )
        clear_button.grid(row=0, column=3)

        model_row = ttk.Frame(control_frame)
        model_row.pack(fill=tk.X, pady=(5, 0))
        model_row.columnconfigure(1, weight=1)
        
        # Model selection
        self.model_label = ttk.Label(
            model_row,
            text=tr("Model:"),
            font=("TkDefaultFont", 10),
            width=8,
            anchor="w"
        )
        self.model_label.grid(
            row=0, column=0, sticky="w", padx=(0, 5)
        )
        
        self.model_menu = ttk.Combobox(
            model_row,
            textvariable=self.model_var,
            values=list(self.model_id_by_label.keys()),
            width=28,
            state="readonly"
        )
        self.model_menu.grid(row=0, column=1, sticky="ew", padx=(0, 5))
        self.model_menu.bind("<<ComboboxSelected>>", self._on_model_changed)

        self.refresh_models_button = ttk.Button(
            model_row,
            text=tr("Refresh"),
            width=5,
            command=lambda: self.refresh_models(show_result=True)
        )
        self.refresh_models_button.grid(row=0, column=2, padx=(0, 5))

        status_row = ttk.Frame(control_frame)
        status_row.pack(fill=tk.X, pady=(5, 0))
        self.thinking_check = ttk.Checkbutton(
            status_row,
            text=tr("Thinking mode"),
            variable=self.thinking_var,
            command=self._persist_thinking_setting,
        )
        self.thinking_check.pack(side=tk.LEFT)
        ttk.Label(
            status_row,
            textvariable=self.model_status_var,
            foreground="gray",
        ).pack(side=tk.RIGHT)
        
        # Chat display area
        self.content_paned = ttk.Panedwindow(self, orient=tk.VERTICAL)
        self.content_paned.grid(
            row=1, column=0, sticky="nsew", padx=5, pady=5
        )

        chat_pane = ttk.Frame(self.content_paned)
        chat_pane.columnconfigure(0, weight=1)
        chat_pane.rowconfigure(0, weight=1)
        self.chat_display = tk.Text(
            chat_pane,
            wrap=tk.WORD,
            width=40,
            height=20
        )
        self.chat_display.grid(row=0, column=0, sticky="nsew")
        self.chat_scrollbar = ttk.Scrollbar(
            chat_pane,
            orient=tk.VERTICAL,
            command=self.chat_display.yview
        )
        self.chat_scrollbar.grid(row=0, column=1, sticky="ns")
        self.chat_display.configure(
            yscrollcommand=self.chat_scrollbar.set
        )
        self.content_paned.add(chat_pane, weight=3)
        self.chat_display.config(
            state=tk.NORMAL,
            takefocus=True,
            selectbackground="#2563EB",
            selectforeground="#FFFFFF",
            inactiveselectbackground="#93C5FD"
        )
        self.chat_display.bind(
            "<ButtonPress-1>",
            lambda event: event.widget.focus_set()
        )
        self.chat_display.bind("<KeyPress>", self._handle_readonly_chat_key)
        self.chat_display.bind("<<Cut>>", lambda event: "break")
        self.chat_display.bind("<<Paste>>", lambda event: "break")
        self._configure_chat_tags()
        
        # Bottom input area and buttons
        input_pane = ttk.Frame(self.content_paned)
        input_pane.columnconfigure(0, weight=1)
        input_pane.rowconfigure(0, weight=1)
        self.content_paned.add(input_pane, weight=1)

        input_frame = ttk.Frame(input_pane)
        input_frame.grid(row=0, column=0, sticky="nsew")
        input_frame.columnconfigure(0, weight=1)
        input_frame.rowconfigure(0, weight=1)
        
        # Input field
        self.input_field = tk.Text(
            input_frame,
            wrap=tk.WORD,
            width=40,
            height=4
        )
        self.input_field.grid(
            row=0, column=0, sticky="nsew"
        )
        self.input_scrollbar = ttk.Scrollbar(
            input_frame,
            orient=tk.VERTICAL,
            command=self.input_field.yview
        )
        self.input_scrollbar.grid(row=0, column=1, sticky="ns")
        self.input_field.configure(
            yscrollcommand=self.input_scrollbar.set
        )
        self.input_field.bind("<Control-Return>", self._send_message)
        self.input_field.bind("<Return>", self._handle_return)
        
        # Keep the input the same width as the chat display and put actions
        # directly below it.
        button_frame = ttk.Frame(input_frame)
        button_frame.grid(
            row=1,
            column=0,
            columnspan=2,
            sticky="ew",
            pady=(5, 0)
        )
        
        # Send button
        send_button = ttk.Button(
            button_frame,
            text=tr("Send"),
            command=self._send_message,
        )
        send_button.pack(
            side=tk.LEFT,
            fill=tk.X,
            expand=True,
            padx=(0, 4)
        )
        
        # Insert code button
        code_button = ttk.Button(
            button_frame,
            text=tr("Insert code"),
            command=self._insert_current_code,
        )
        code_button.pack(
            side=tk.LEFT,
            fill=tk.X,
            expand=True,
            padx=(4, 0)
        )

        for widget in (self, self.chat_display, self.input_field):
            widget.bind(
                "<<ThemeChanged>>",
                self._on_theme_changed,
                add="+"
            )
        self._apply_theme_colors()
        self.after(150, self._set_initial_pane_split)

        self._context_selected_text = ""
        self._context_widget = None
        self.text_context_menu = tk.Menu(self, tearoff=False)
        self.text_context_menu.add_command(
            label=tr("Copy"),
            command=self._copy_context_text
        )
        self.text_context_menu.add_command(
            label=tr("Insert"),
            command=self._insert_context_text
        )
        self._bind_text_context_menu(self.chat_display)
        self._bind_text_context_menu(self.input_field)
        
        # If API key is not set, show a notice
        provider = self._current_provider()
        if provider is not None and not provider.get("api_key"):
            self.after(500, self._show_api_key_notice)

    def _bind_text_context_menu(self, widget):
        """Attach the copy/insert menu to a Tk text widget."""
        widget.bind(
            "<Button-3>",
            lambda event, target=widget: self._show_text_context_menu(
                event,
                target
            )
        )

    def _handle_readonly_chat_key(self, event):
        """Allow selection and copy while preventing edits to chat output."""
        keysym = getattr(event, "keysym", "")
        if keysym in ("BackSpace", "Delete", "Return", "KP_Enter"):
            return "break"
        if event.state & 0x0004 and keysym.lower() in ("v", "x"):
            return "break"
        if getattr(event, "char", "") and not (event.state & 0x0004):
            return "break"
        return None

    def _show_text_context_menu(self, event, widget):
        """Show copy and insert actions for the current selection."""
        widget.focus_set()
        selected_text = get_widget_selection_text(widget)
        self._context_selected_text = selected_text or ""
        self._context_widget = widget
        state = tk.NORMAL if self._context_selected_text else tk.DISABLED
        self.text_context_menu.entryconfigure(0, state=state)
        self.text_context_menu.entryconfigure(1, state=state)
        try:
            self.text_context_menu.tk_popup(event.x_root, event.y_root)
        finally:
            self.text_context_menu.grab_release()
        return "break"

    def _copy_context_text(self):
        """Copy the selected text to the system clipboard."""
        if not self._context_selected_text:
            return
        self.clipboard_clear()
        self.clipboard_append(self._context_selected_text)
        self.update_idletasks()

    def _insert_context_text(self):
        """Insert the selected text at the current editor cursor."""
        if not self._context_selected_text:
            return
        editor = get_current_editor()
        if editor is None:
            messagebox.showinfo(
                tr("Notice"),
                tr("Open a code file first."),
            )
            return
        if not insert_text_at_editor_cursor(
            editor,
            self._context_selected_text
        ):
            messagebox.showerror(
                tr("Insert failed"),
                tr("Could not locate the text cursor in the current editor."),
            )

    def _configure_chat_tags(self):
        """Configure rich text fonts, then apply the current theme colors."""
        self.chat_display.tag_configure(
            "assistant_heading_1",
            font=("TkDefaultFont", 12, "bold")
        )
        self.chat_display.tag_configure(
            "assistant_heading_2",
            font=("TkDefaultFont", 11, "bold")
        )
        self.chat_display.tag_configure(
            "assistant_heading_n",
            font=("TkDefaultFont", 10, "bold")
        )
        self.chat_display.tag_configure(
            "assistant_code",
            font=("Consolas", 10)
        )
        self.chat_display.tag_configure(
            "assistant_inline_code",
            font=("Consolas", 10)
        )
        self.chat_display.tag_configure(
            "conversation_divider",
            font=("TkDefaultFont", 10, "bold"),
            justify="center"
        )
        self.chat_display.tag_configure(
            "user_prefix",
            font=("TkDefaultFont", 10, "bold")
        )
        self.chat_display.tag_configure(
            "assistant_prefix",
            font=("TkDefaultFont", 10, "bold")
        )
        self._apply_theme_colors()

    def _on_theme_changed(self, event=None):
        """Apply new colors after Thonny finishes changing the UI theme."""
        self.after_idle(self._apply_theme_colors)

    def _set_initial_pane_split(self):
        """Give the chat more initial room while keeping input usable."""
        try:
            height = self.content_paned.winfo_height()
            if height > 180:
                self.content_paned.sashpos(0, int(height * 0.75))
        except tk.TclError:
            pass

    def _resolve_theme_color(self, value, fallback):
        """Resolve Tk system color names to a normal hex color."""
        try:
            red, green, blue = self.chat_display.winfo_rgb(value)
            return f"#{red // 256:02X}{green // 256:02X}{blue // 256:02X}"
        except (TypeError, tk.TclError):
            return fallback

    def _apply_theme_colors(self):
        """Update text and tag colors to match the active Thonny theme."""
        style = ttk.Style(self)
        dark_theme = False
        try:
            dark_theme = bool(get_workbench().uses_dark_ui_theme())
        except Exception:
            pass

        background = self._resolve_theme_color(
            style.lookup("Text", "background"),
            "#FFFFFF"
        )
        foreground = self._resolve_theme_color(
            style.lookup("Text", "foreground"),
            "#E8EAED" if dark_theme else "#000000"
        )
        if not dark_theme:
            try:
                red, green, blue = self.chat_display.winfo_rgb(background)
                dark_theme = (red * 299 + green * 587 + blue * 114) < 40000
            except tk.TclError:
                pass

        if dark_theme:
            palette = {
                "text": "#E8EAED",
                "user_text": "#D1D5DB",
                "code": "#FF8A80",
                "code_bg": "#2B2B2B",
                "heading_1": "#D8B4FE",
                "heading_2": "#93C5FD",
                "heading_n": "#5EEAD4",
                "user_prefix": "#60A5FA",
                "assistant_prefix": "#4ADE80",
                "error": "#F87171",
                "muted": "#9CA3AF",
                "select_bg": "#2563EB",
                "select_fg": "#FFFFFF",
                "inactive_select_bg": "#1E40AF",
            }
        else:
            palette = {
                "text": "#111827",
                "user_text": "#111827",
                "code": "#B91C1C",
                "code_bg": "#F3F4F6",
                "heading_1": "#6B21A8",
                "heading_2": "#1D4ED8",
                "heading_n": "#047857",
                "user_prefix": "#1D4ED8",
                "assistant_prefix": "#047857",
                "error": "#B91C1C",
                "muted": "#6B7280",
                "select_bg": "#2563EB",
                "select_fg": "#FFFFFF",
                "inactive_select_bg": "#93C5FD",
            }

        for widget in (self.chat_display, getattr(self, "input_field", None)):
            if widget is None:
                continue
            widget.configure(
                background=background,
                foreground=palette["text"],
                insertbackground=palette["text"],
                selectbackground=palette["select_bg"],
                selectforeground=palette["select_fg"],
                inactiveselectbackground=palette["inactive_select_bg"]
            )

        self.chat_display.tag_configure(
            "assistant_text",
            foreground=palette["text"]
        )
        self.chat_display.tag_configure(
            "assistant_heading_1",
            foreground=palette["heading_1"]
        )
        self.chat_display.tag_configure(
            "assistant_heading_2",
            foreground=palette["heading_2"]
        )
        self.chat_display.tag_configure(
            "assistant_heading_n",
            foreground=palette["heading_n"]
        )
        self.chat_display.tag_configure(
            "assistant_code",
            foreground=palette["code"],
            background=palette["code_bg"]
        )
        self.chat_display.tag_configure(
            "assistant_inline_code",
            foreground=palette["code"]
        )
        self.chat_display.tag_configure(
            "conversation_divider",
            foreground=palette["muted"]
        )
        self.chat_display.tag_configure(
            "notice",
            foreground=palette["error"]
        )
        self.chat_display.tag_configure(
            "waiting",
            foreground=palette["muted"]
        )
        self.chat_display.tag_configure(
            "error",
            foreground=palette["error"]
        )
        self.chat_display.tag_configure(
            "user_prefix",
            foreground=palette["user_prefix"]
        )
        self.chat_display.tag_configure(
            "user_msg",
            foreground=palette["user_text"]
        )
        self.chat_display.tag_configure(
            "assistant_prefix",
            foreground=palette["assistant_prefix"]
        )
        self.chat_display.tag_configure(
            "sel",
            background=palette["select_bg"],
            foreground=palette["select_fg"]
        )
        self.chat_display.tag_raise("sel")

    def _insert_inline_styled_line(self, line):
        """Insert normal text with inline code highlighted."""
        position = 0
        for match in re.finditer(r"`([^`\n]+)`", line):
            if match.start() > position:
                self.chat_display.insert(
                    tk.END,
                    line[position:match.start()],
                    "assistant_text"
                )
            self.chat_display.insert(
                tk.END,
                match.group(1),
                "assistant_inline_code"
            )
            position = match.end()
        if position < len(line):
            self.chat_display.insert(
                tk.END,
                line[position:],
                "assistant_text"
            )

    def _render_assistant_markdown(self, text, start_mark=None):
        """Render assistant text with code and heading tags."""
        self.chat_display.config(state=tk.NORMAL)
        if start_mark is not None:
            self.chat_display.delete(start_mark, tk.END)

        in_code_block = False
        for line in text.splitlines(keepends=True):
            content = line.rstrip("\r\n")
            newline = "\n" if line.endswith(("\n", "\r")) else ""

            if content.lstrip().startswith("```"):
                in_code_block = not in_code_block
                continue

            if in_code_block:
                self.chat_display.insert(
                    tk.END,
                    content + newline,
                    "assistant_code"
                )
                continue

            heading = re.match(
                r"^\s{0,3}(#{1,6})\s+(.*)$",
                content
            )
            if heading:
                level = len(heading.group(1))
                tag = (
                    "assistant_heading_1"
                    if level == 1
                    else "assistant_heading_2"
                    if level == 2
                    else "assistant_heading_n"
                )
                self.chat_display.insert(
                    tk.END,
                    heading.group(2) + newline,
                    tag
                )
                continue

            self._insert_inline_styled_line(content)
            if newline:
                self.chat_display.insert(
                    tk.END,
                    newline,
                    "assistant_text"
                )

        self.chat_display.config(state=tk.NORMAL)
        self.chat_display.see(tk.END)

    def _prepare_provider_choices(self, config, preferred_provider_id):
        """Normalize providers and build provider-name mappings."""
        providers = normalize_providers(config.get("providers"))
        if not providers:
            providers = [copy.deepcopy(DEFAULT_PROVIDER)]
        config["providers"] = providers

        self._provider_id_by_label = {}
        self._label_by_provider_id = {}
        for provider in providers:
            label = provider["name"]
            if label in self._provider_id_by_label:
                label = f"{label} ({provider['id']})"
            self._provider_id_by_label[label] = provider["id"]
            self._label_by_provider_id[provider["id"]] = label

        if preferred_provider_id not in self._label_by_provider_id:
            preferred_provider_id = providers[0]["id"]
        config["provider_id"] = preferred_provider_id
        return preferred_provider_id

    def _current_provider(self):
        """Return the currently selected provider dictionary."""
        return get_provider(self.config, self.config.get("provider_id"))

    def _selected_provider_id(self):
        """Return the provider ID for the current provider selector."""
        label = self.provider_var.get()
        return self._provider_id_by_label.get(
            label,
            self.config.get("provider_id")
        )

    def _persist_thinking_setting(self, event=None):
        """Persist the thinking-mode switch shown in the main panel."""
        self.config["enable_thinking"] = bool(self.thinking_var.get())
        save_config(self.config)

    def _prepare_model_choices(
        self,
        models,
        preferred_model_id,
        use_fallback=True
    ):
        """Build label-to-ID mappings and return the selected model ID."""
        normalized = normalize_models(models)
        if not normalized and use_fallback:
            normalized = [model.copy() for model in FALLBACK_MODELS]

        self.available_models = normalized
        self.model_id_by_label = {}
        self.label_by_model_id = {}
        for model in normalized:
            label = format_model_label(model)
            if label in self.model_id_by_label:
                label = f"{label} ({model['id']})"
            self.model_id_by_label[label] = model["id"]
            self.label_by_model_id[model["id"]] = label

        if not normalized:
            return None
        if preferred_model_id not in self.label_by_model_id:
            preferred_model_id = (
                DEFAULT_MODEL_ID
                if DEFAULT_MODEL_ID in self.label_by_model_id
                else normalized[0]["id"]
            )
        return preferred_model_id

    def _apply_model_choices(self, models, preferred_model_id):
        """Update the selector with API models and persist the selection."""
        selected_model_id = self._prepare_model_choices(
            models, preferred_model_id
        )
        self.model_var.set(self.label_by_model_id[selected_model_id])
        self.model_menu.configure(values=list(self.model_id_by_label.keys()))
        provider = self._current_provider()
        if provider is not None:
            provider["models"] = self.available_models
            provider["model"] = selected_model_id or ""
        save_config(self.config)
        return selected_model_id

    def _selected_model_id(self):
        """Return the API model ID for the current combobox selection."""
        label = self.model_var.get()
        return self.model_id_by_label.get(label, "")

    def _on_model_changed(self, event=None):
        """Persist the selected model for the current provider."""
        provider = self._current_provider()
        if provider is not None:
            provider["model"] = self._selected_model_id()
        self.config["temperature"] = self.temp_var.get()
        self.config["max_tokens"] = self.max_tokens_var.get()
        self.config["enable_thinking"] = bool(self.thinking_var.get())
        save_config(self.config)

    def _on_provider_changed(self, event=None):
        """Load the selected provider's saved models and configuration."""
        provider_id = self._selected_provider_id()
        self.config["provider_id"] = provider_id
        provider = self._current_provider()
        if provider is None:
            return

        selected_model_id = self._prepare_model_choices(
            provider.get("models", []),
            provider.get("model", ""),
            use_fallback=False
        )
        self.model_var.set(
            self.label_by_model_id[selected_model_id]
            if selected_model_id
            else tr("Fetch a model first")
        )
        self.model_menu.configure(values=list(self.model_id_by_label.keys()))
        self.model_status_var.set(
            tr(
                "Loaded {count} models",
                count=len(self.available_models),
            )
        )
        save_config(self.config)

        if provider.get("api_key"):
            self.refresh_models(show_result=False)
        else:
            self._show_api_key_notice()

    def refresh_models(self, show_result=False):
        """Refresh the current provider's models from its /models endpoint."""
        if self._models_loading:
            return
        if not _ensure_openai_sdk_available():
            if show_result:
                _show_openai_sdk_error()
            return

        provider = self._current_provider()
        if provider is None:
            return
        if not provider.get("api_key"):
            if show_result:
                messagebox.showwarning(
                    tr("Set API Key first"),
                    tr(
                        "Enter the API Key for the current provider in "
                        "Settings."
                    ),
                )
            self.model_status_var.set(
                tr("Set API Key first")
            )
            return

        self._models_loading = True
        self.refresh_models_button.state(["disabled"])
        self.model_status_var.set(
            tr(
                "{provider}: syncing models...",
                provider=provider["name"],
            )
        )
        threading.Thread(
            target=self._fetch_models,
            args=(copy.deepcopy(provider), show_result),
            daemon=True
        ).start()

    def _fetch_models(self, provider, show_result):
        """Fetch a provider's authenticated model list in a worker thread."""
        api_key = provider.get("api_key", "")
        try:
            client = OpenAI(
                api_key=api_key,
                base_url=provider["api_base"],
                timeout=30.0,
                max_retries=1
            )
            response = client.models.list()
            models = normalize_models(response.data)
            if not models:
                raise RuntimeError(
                    tr("The provider returned an empty model list.")
                )
            self._model_results.put(
                ("success", provider["id"], models, show_result)
            )
        except Exception as e:
            error_text = str(e)
            if api_key:
                error_text = error_text.replace(
                    api_key,
                    tr("[API Key hidden]"),
                )
            self._model_results.put(
                ("error", provider["id"], error_text, show_result)
            )

    def _poll_model_results(self):
        """Apply model-list worker results on Tk's main thread."""
        try:
            while True:
                result_type, provider_id, payload, show_result = (
                    self._model_results.get_nowait()
                )
                self._models_loading = False
                self.refresh_models_button.state(["!disabled"])
                provider = get_provider(self.config, provider_id)
                provider_name = provider["name"] if provider else tr("Provider")
                if result_type == "success":
                    if provider is not None:
                        provider["models"] = normalize_models(payload)
                        provider_model_ids = {
                            model["id"] for model in provider["models"]
                        }
                        if provider.get("model") not in provider_model_ids:
                            provider["model"] = (
                                provider["models"][0]["id"]
                                if provider["models"]
                                else ""
                            )
                    save_config(self.config)

                    selected_label = ""
                    if self.config.get("provider_id") == provider_id:
                        selected_id = self._apply_model_choices(
                            payload,
                            self._selected_model_id()
                        )
                        selected_label = self.label_by_model_id[selected_id]
                        self.model_status_var.set(
                            tr(
                                "{provider}: synced {count} models",
                                provider=provider_name,
                                count=len(payload),
                            )
                        )
                    if show_result:
                        messagebox.showinfo(
                            tr("Model list updated"),
                            tr(
                                "Provider: {provider}\n"
                                "Current model: {model}\n"
                                "{count} models available.",
                                provider=provider_name,
                                model=selected_label or tr("Saved"),
                                count=len(payload),
                            ),
                        )
                else:
                    if self.config.get("provider_id") == provider_id:
                        self.model_status_var.set(
                            tr(
                                "{provider}: sync failed",
                                provider=provider_name,
                            )
                        )
                    if show_result:
                        messagebox.showerror(
                            tr("Failed to fetch model list"),
                            f"{payload}\n\n"
                            + tr(
                                "The plugin will keep the provider's cached "
                                "model list."
                            ),
                        )
                current_provider = self._current_provider()
                if (
                    current_provider is not None
                    and current_provider["id"] != provider_id
                    and current_provider.get("api_key")
                ):
                    self.after(0, self.refresh_models)
        except queue.Empty:
            pass
        finally:
            if self.winfo_exists():
                self.after(100, self._poll_model_results)
    
    def _show_api_key_notice(self):
        """Show a notice when the current provider has no API key."""
        provider = self._current_provider()
        provider_name = (
            provider["name"] if provider else tr("Current provider")
        )
        self.chat_display.config(state=tk.NORMAL)
        self.chat_display.insert(
            tk.END,
            tr(
                "⚠️ Click ⚙️ in the top-right corner to set the API base URL "
                "and API Key for “{provider}”.",
                provider=provider_name,
            )
            + "\n\n",
            "notice"
        )
        self.chat_display.tag_configure("notice", foreground="red")
        self.chat_display.config(state=tk.NORMAL)
    
    def _show_settings(self):
        """Open the multi-provider settings dialog."""
        ProviderSettingsDialog(
            self,
            self.config,
            on_saved=self._on_settings_saved
        )

    def _on_settings_saved(self, config, provider_id):
        """Apply updated provider settings and fetch the provider's models."""
        self.config = config
        self._prepare_provider_choices(config, provider_id)
        provider = self._current_provider()
        self.provider_var.set(self._label_by_provider_id[provider["id"]])

        selected_model_id = self._prepare_model_choices(
            provider.get("models", []),
            provider.get("model", ""),
            use_fallback=False
        )
        self.model_var.set(
            self.label_by_model_id[selected_model_id]
            if selected_model_id
            else tr("Fetch a model first")
        )
        self.model_menu.configure(values=list(self.model_id_by_label.keys()))
        self.temp_var.set(
            float(
                config.get(
                    "temperature",
                    DEFAULT_CONFIG["temperature"],
                )
            )
        )
        self.max_tokens_var.set(
            normalize_output_tokens(
                config.get("max_tokens", DEFAULT_CONFIG["max_tokens"])
            )
        )
        self.thinking_var.set(
            bool(config.get("enable_thinking", False))
        )
        self.model_status_var.set(tr("Fetching provider models..."))
        save_config(self.config)
        self.after(0, lambda: self.refresh_models(show_result=True))
    
    def _clear_chat(self):
        """Clear chat history"""
        if messagebox.askyesno(
            tr("Confirm"),
            tr("Clear all chat history?"),
        ):
            self.messages = []
            self.config["chat_history"] = []
            save_config(self.config)
            
            self.chat_display.config(state=tk.NORMAL)
            self.chat_display.delete("1.0", tk.END)
            self.chat_display.config(state=tk.NORMAL)
    
    def _load_chat_history(self):
        """Load chat history"""
        self.chat_display.config(state=tk.NORMAL)
        
        previous_role = None
        for msg in self.messages:
            if msg["role"] == "user" and previous_role == "assistant":
                self._insert_conversation_divider()
            if msg["role"] == "user":
                self._display_user_message(msg["content"])
            elif msg["role"] == "assistant":
                self._display_assistant_message(msg["content"])
            previous_role = msg["role"]
                
        self.chat_display.config(state=tk.NORMAL)
        self.chat_display.see(tk.END)
    
    def _send_message(self, event=None):
        """Send a message through the selected provider and model."""
        if self._request_pending:
            return
        if not _ensure_openai_sdk_available():
            _show_openai_sdk_error()
            return
            
        provider = self._current_provider()
        if provider is None:
            messagebox.showerror(
                tr("No provider"),
                tr("Configure a model provider in Settings first."),
            )
            return
        if not provider.get("api_key"):
            messagebox.showerror(
                tr("Set API Key first"),
                tr(
                    "Set the API Key for “{provider}” first.",
                    provider=provider["name"],
                ),
            )
            return
        model_id = self._selected_model_id()
        if not model_id:
            messagebox.showerror(
                tr("No model selected"),
                tr(
                    "Fetch and select a model for the current provider first."
                ),
            )
            return
            
        # Get original input text
        original_text = self.input_field.get("1.0", tk.END).strip()
        if not original_text:
            return
        
        # Clear input field
        self.input_field.delete("1.0", tk.END)
        
        # Add context prefix to the text actually sent to API
        if "```python" in original_text or "分析" in original_text or "analyze this code" in original_text.lower():
            # If already contains code block, add Thonny IDE context
            prompt_prefix = tr(
                "I am writing Python code in Thonny IDE. Analyze the "
                "following code and suggest improvements:"
            )
            text_to_display = original_text
            text_to_send = f"{prompt_prefix}\n\n{original_text}"
        else:
            # General conversation content
            text_to_display = original_text
            text_to_send = original_text
        
        # Display user message (show original text, without prefix)
        if self.messages and self.messages[-1].get("role") == "assistant":
            self._insert_conversation_divider()
        self._display_user_message(text_to_display)
        
        # Add message with prefix to chat history
        self.messages.append({"role": "user", "content": text_to_send})
        
        # Show waiting message
        self.chat_display.config(state=tk.NORMAL)
        wait_msg_index = self.chat_display.index(tk.END)
        self.chat_display.insert(
            tk.END,
            tr(
                "{provider} is thinking...",
                provider=provider["name"],
            )
            + "\n\n",
            "waiting"
        )
        self.chat_display.tag_configure("waiting", foreground="gray")
        self.chat_display.config(state=tk.NORMAL)
        self.chat_display.see(tk.END)
        
        # Call API in new thread
        interpreter_context = get_current_interpreter_context()
        system_prompt = compose_system_prompt(
            self.config.get("system_prompt", ""),
            interpreter_context
        )
        request_messages = [{
            "role": "system",
            "content": system_prompt
        }]
        request_messages.extend(self.messages)
        self._request_pending = True
        self._streaming_started = False
        self._streaming_text = ""
        threading.Thread(
            target=self._call_ai_api,
            args=(
                wait_msg_index,
                request_messages,
                model_id,
                self.temp_var.get(),
                self.max_tokens_var.get(),
                bool(self.thinking_var.get()),
                copy.deepcopy(provider)
            ),
            name="AIStreamWorker",
            daemon=True
        ).start()
    
    def _call_ai_api(
        self,
        wait_msg_index,
        messages,
        model,
        temperature,
        max_tokens,
        enable_thinking,
        provider
    ):
        """Call the selected provider's chat-completions API."""
        api_key = provider.get("api_key", "")
        try:
            client = OpenAI(
                api_key=api_key,
                base_url=provider["api_base"],
                timeout=60.0,
                max_retries=2
            )
            request_args = {
                "model": model,
                "messages": messages,
                "max_tokens": max_tokens,
                "temperature": temperature,
                "stream": True
            }
            requested_args = dict(request_args)
            thinking_configured = configure_thinking_in_request(
                requested_args,
                provider,
                enable_thinking,
            )

            def consume_stream(stream):
                received_content = False
                reasoning_chars = 0
                finish_reason = None
                for chunk in stream:
                    choices = getattr(chunk, "choices", None) or []
                    if not choices:
                        continue
                    choice = choices[0]
                    delta = getattr(choice, "delta", None)
                    content = getattr(delta, "content", None)
                    reasoning_content = getattr(
                        delta, "reasoning_content", None
                    )
                    if reasoning_content:
                        reasoning_chars += len(reasoning_content)
                    if content:
                        received_content = True
                        self._api_results.put(
                            (
                                "chunk",
                                wait_msg_index,
                                content,
                                provider["name"]
                            )
                        )
                    finish = getattr(choice, "finish_reason", None)
                    if finish:
                        finish_reason = finish
                return received_content, reasoning_chars, finish_reason

            stream = client.chat.completions.create(**requested_args)
            received_content, reasoning_chars, finish_reason = (
                consume_stream(stream)
            )

            if not received_content:
                details = []
                if reasoning_chars:
                    details.append(
                        tr(
                            "Received only {count} characters of reasoning "
                            "content",
                            count=reasoning_chars,
                        )
                    )
                if finish_reason:
                    details.append(
                        tr(
                            "Finish reason: {reason}",
                            reason=finish_reason,
                        )
                    )
                separator = "；" if get_ui_language() == "zh" else "; "
                detail_text = separator.join(details) or tr(
                    "No text content in the stream"
                )
                if enable_thinking:
                    thinking_text = tr(
                        "Thinking mode was enabled and was not turned off "
                        "automatically."
                    )
                elif thinking_configured:
                    thinking_text = tr(
                        "Thinking mode was disabled according to the settings."
                    )
                else:
                    thinking_text = tr(
                        "The current provider did not expose a recognizable "
                        "parameter for disabling thinking mode."
                    )
                raise RuntimeError(
                    tr(
                        "The provider returned no text content ({details}). "
                        "{thinking_status}; current output limit: "
                        "{max_tokens} tokens.",
                        details=detail_text,
                        thinking_status=thinking_text,
                        max_tokens=max_tokens,
                    )
                )
            self._api_results.put(
                ("done", wait_msg_index, "", provider["name"])
            )
        except Exception as e:
            error_text = str(e)
            if api_key:
                error_text = error_text.replace(
                    api_key,
                    tr("[API Key hidden]"),
                )
            self._api_results.put(
                ("error", wait_msg_index, error_text, provider["name"])
            )

    def _poll_api_results(self):
        """Apply queued stream results on Tk's main thread in batches."""
        pending_parts = []
        pending_wait_index = None
        pending_provider_name = None
        terminal_event = None
        try:
            while True:
                (
                    result_type,
                    wait_msg_index,
                    content,
                    provider_name
                ) = self._api_results.get_nowait()
                if result_type == "chunk":
                    if pending_wait_index is None:
                        pending_wait_index = wait_msg_index
                        pending_provider_name = provider_name
                    pending_parts.append(content)
                else:
                    terminal_event = (
                        result_type,
                        wait_msg_index,
                        content,
                        provider_name
                    )
        except queue.Empty:
            pass
        finally:
            if pending_parts:
                self._handle_api_chunk(
                    pending_wait_index,
                    "".join(pending_parts),
                    pending_provider_name
                )
            if terminal_event is not None:
                result_type, wait_msg_index, content, provider_name = (
                    terminal_event
                )
                if result_type == "done":
                    self._handle_api_done(wait_msg_index, provider_name)
                else:
                    self._handle_api_error(
                        wait_msg_index, content, provider_name
                    )
            if self.winfo_exists():
                self.after(100, self._poll_api_results)

    def _handle_api_chunk(
        self,
        wait_msg_index,
        content,
        provider_name="AI"
    ):
        """Append a streamed response chunk."""
        self.chat_display.config(state=tk.NORMAL)
        if not self._streaming_started:
            self.chat_display.delete(
                wait_msg_index,
                wait_msg_index + "+1l"
            )
            self.chat_display.insert(
                tk.END,
                f"🤖 {provider_name}：",
                "assistant_prefix"
            )
            self.chat_display.tag_configure(
                "assistant_prefix",
                foreground="green",
                font=("TkDefaultFont", 10, "bold")
            )
            self._streaming_started = True
            self.chat_display.mark_set(
                self._streaming_start_mark,
                "end-1c"
            )
            self.chat_display.mark_gravity(
                self._streaming_start_mark,
                "left"
            )

        self._streaming_text += content
        self._render_assistant_markdown(
            self._streaming_text,
            self._streaming_start_mark
        )

    def _handle_api_done(self, wait_msg_index, provider_name="AI"):
        """Finish a streamed response and save chat history."""
        self._request_pending = False
        assistant_response = self._streaming_text
        if not self._streaming_started or not assistant_response:
            self._handle_api_error(
                wait_msg_index,
                tr("The provider returned no text content."),
                provider_name
            )
            return

        self.chat_display.config(state=tk.NORMAL)
        self.chat_display.insert(tk.END, "\n\n", "assistant_text")
        self.chat_display.config(state=tk.NORMAL)
        self.chat_display.see(tk.END)
        self.chat_display.mark_unset(self._streaming_start_mark)
        self.messages.append({
            "role": "assistant",
            "content": assistant_response
        })
        self.config["chat_history"] = self.messages
        save_config(self.config)

    def _handle_api_error(
        self,
        wait_msg_index,
        error_text,
        provider_name="AI"
    ):
        """Render a provider API error without exposing the API key."""
        self._request_pending = False
        self.chat_display.config(state=tk.NORMAL)
        if not self._streaming_started:
            self.chat_display.delete(
                wait_msg_index,
                wait_msg_index + "+1l"
            )
        else:
            self.chat_display.insert(tk.END, "\n\n", "assistant_text")
        self.chat_display.insert(
            tk.END,
            tr(
                "{provider} streaming request failed: {error}\n"
                "Check the API Key, account balance, model name, and "
                "network connection.",
                provider=provider_name,
                error=error_text,
            )
            + "\n\n",
            "error"
        )
        self.chat_display.tag_configure("error", foreground="red")
        self.chat_display.config(state=tk.NORMAL)
        self.chat_display.see(tk.END)
    
    def _display_user_message(self, text):
        """Display user message"""
        self.chat_display.config(state=tk.NORMAL)
        self.chat_display.insert(tk.END, tr("👤 Me:"), "user_prefix")
        self.chat_display.insert(tk.END, text + "\n\n", "user_msg")
        self.chat_display.config(state=tk.NORMAL)
        self.chat_display.see(tk.END)

    def _insert_conversation_divider(self):
        """Insert a visual divider between completed conversations."""
        self.chat_display.config(state=tk.NORMAL)
        self.chat_display.insert(
            tk.END,
            "----------------------------------------\n\n",
            "conversation_divider"
        )
        self.chat_display.config(state=tk.NORMAL)
        self.chat_display.see(tk.END)
    
    def _display_assistant_message(self, text, provider_name="AI"):
        """Display assistant message"""
        self.chat_display.config(state=tk.NORMAL)
        self.chat_display.insert(
            tk.END,
            f"🤖 {provider_name}：",
            "assistant_prefix"
        )
        self._render_assistant_markdown(text)
        self.chat_display.config(state=tk.NORMAL)
        self.chat_display.insert(tk.END, "\n\n", "assistant_text")
        self.chat_display.tag_configure(
            "assistant_prefix",
            foreground="green",
            font=("TkDefaultFont", 10, "bold")
        )
        self.chat_display.config(state=tk.NORMAL)
        self.chat_display.see(tk.END)
    
    def _insert_current_code(self):
        """Insert selected code, or the whole editor when nothing is selected."""
        try:
            editor = get_current_editor()
            if editor:
                selected_code = get_editor_selection_text(editor)
                if selected_code:
                    code = selected_code
                    prompt = tr("Analyze the selected code:") + "\n"
                else:
                    code = get_editor_text(editor)
                    prompt = tr("Analyze the complete code:") + "\n"
                if code and code.strip():
                    # Add code to input field
                    current_text = self.input_field.get("1.0", tk.END).strip()
                    
                    if current_text:
                        current_text += "\n\n"
                    
                    current_text += "```python\n" + code + "```\n\n" + prompt
                    
                    self.input_field.delete("1.0", tk.END)
                    self.input_field.insert("1.0", current_text)
                else:
                    messagebox.showinfo(
                        tr("Notice"),
                        tr("There is no code in the current editor to send."),
                    )
            else:
                messagebox.showinfo(
                    tr("Notice"),
                    tr("Open a code file first."),
                )
        except Exception as e:
            messagebox.showerror(
                tr("Read failed"),
                tr("Could not read the current code: {error}", error=str(e)),
            )
    
    def prepare_code_analysis(self):
        """Prepare code analysis, insert code into input field and focus window if code exists"""
        editor = get_current_editor()
        if editor:
            code = get_editor_text(editor)
            if code and code.strip():
                # Add code to input field
                current_text = (
                    "```python\n"
                    + code
                    + "```\n\n"
                    + tr("Analyze this code:")
                    + "\n"
                )
                
                self.input_field.delete("1.0", tk.END)
                self.input_field.insert("1.0", current_text)
                
                # Focus input field
                self.input_field.focus_set()
                
                # Ensure this panel is visible
                wb = get_workbench()
                wb.show_view("AIChatView")
                
                return True
        return False

    def _handle_return(self, event):
        """Handle Enter key press event"""
        # Check if Enter key is pressed without Ctrl key
        if not (event.state & 0x0004):  # 0x0004 represents Control key
            # Get current text content
            text = self.input_field.get("1.0", tk.END).strip()
            
            # If content is not empty, send message
            if text:
                self._send_message()
                return "break"  # Prevent original Enter key behavior (newline)
            else:
                # If input field is empty, allow newline (normal behavior)
                return None
        # For Ctrl+Enter, keep original behavior (add newline)
        return None

# Toolbar command that opens the thonny-ai-assistant panel.
def thonny_ai_assistant():
    """Show the AI assistant panel."""
    global _global_ai_chat_view
    
    if not _ensure_openai_sdk_available():
        _show_openai_sdk_error()
        return
    
    # If side panel is not yet created, ensure it's visible
    wb = get_workbench()
    wb.show_view("AIChatView")
    
    # If side panel instance exists, use it directly
    if _global_ai_chat_view:
        # Ask whether to analyze current code
        editor = get_current_editor()
        if editor:
            code = get_editor_text(editor)
            if code and code.strip():
                use_code = messagebox.askyesno(
                    tr("Code analysis"),
                    tr(
                        "Send the code in the current editor to AI for "
                        "analysis?"
                    ),
                )
                if use_code:
                    _global_ai_chat_view.prepare_code_analysis()
    else:
        messagebox.showinfo(
            tr("Notice"),
            tr("Open AI Assistant from the View menu first."),
        )
