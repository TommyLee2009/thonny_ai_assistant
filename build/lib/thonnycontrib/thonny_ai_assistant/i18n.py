"""Small localization layer for the Thonny AI Assistant plugin."""

from thonny import get_workbench


_UI_LANGUAGE = None


_ZH_CN = {
    "AI Assistant": "AI助手",
    "Open AI Assistant": "打开 AI助手",
    "AI Assistant Settings": "AI助手设置",
    "Manage AI providers, API endpoints, and API keys": (
        "管理 AI 模型供应商、API 地址和 API Key"
    ),
    "OpenAI-compatible SDK is required: pip install \"openai>=1.75.0\"": (
        "请先安装 OpenAI 兼容 SDK：pip install \"openai>=1.75.0\""
    ),
    "Current interpreter: {executable}": "当前解释器：{executable}",
    "Import error: {error_type}: {error}": "导入错误：{error_type}: {error}",
    "Missing dependency": "缺少依赖",
    "Not set": "未设置",
    "Provider {index}": "供应商 {index}",
    "Unknown": "未知",
    "Default provider": "默认供应商",
    "Current interpreter environment: {description}": (
        "当前使用的解释器环境是：{description}"
    ),
    "Thonny interpreter type: {backend_name}": (
        "Thonny 解释器类型标识：{backend_name}"
    ),
    "Interpreter executable: {executable}": (
        "解释器可执行文件：{executable}"
    ),
    (
        "Use this interpreter environment to determine the available syntax, "
        "standard library, third-party packages, and hardware APIs. Do not "
        "assume the user is running desktop CPython."
    ): (
        "请根据该解释器环境判断可用语法、标准库、第三方包和硬件 API；"
        "不要默认用户运行在普通桌面版 CPython 中。"
    ),
    "Provider name:": "供应商名称：",
    "API base URL:": "API 地址：",
    "API Key:": "API Key：",
    "Supports OpenAI-compatible /models and /chat/completions endpoints.": (
        "支持 OpenAI 兼容的 /models 和 /chat/completions 接口。"
    ),
    "System prompt:": "系统提示词：",
    (
        "Define the AI role, response structure, and quality requirements. "
        "Thonny compiler/interpreter information is still added automatically."
    ): (
        "可定义 AI 的角色、回答结构和质量要求；"
        "Thonny 的编译器/解释器信息仍会自动追加。"
    ),
    "Add provider": "新增供应商",
    "Delete current": "删除当前",
    "Cancel": "取消",
    "Save and fetch models": "保存并获取模型",
    "Saved key: {key}; leave blank to keep it": (
        "已保存 Key：{key}；留空保持不变"
    ),
    "API Key is required for a new provider.": (
        "新增供应商时必须填写 API Key"
    ),
    "Provider not found": "未找到供应商",
    "Select a provider to delete first.": "请先选择要删除的供应商。",
    "Delete provider": "删除供应商",
    "Delete “{provider}” and its local configuration?": (
        "确定删除“{provider}”及其本地配置吗？"
    ),
    "Missing name": "缺少名称",
    "Enter a provider name.": "请输入供应商名称。",
    "Invalid API base URL": "API 地址无效",
    "Enter an API base URL beginning with http:// or https://.": (
        "请输入以 http:// 或 https:// 开头的 API 地址。"
    ),
    "Duplicate provider name": "供应商名称重复",
    "Use a different provider name.": "请使用不同的供应商名称。",
    "Missing API Key": "缺少 API Key",
    "Enter the API Key for this provider.": "请输入该供应商的 API Key。",
    "Fetch a model first": "请先获取模型",
    "Loaded {count} models": "已加载 {count} 个模型",
    "Provider:": "供应商：",
    "Model:": "模型：",
    "Generation settings": "生成参数",
    "Refresh": "刷新",
    "Temperature:": "温度：",
    "Output tokens:": "输出 tokens：",
    "Thinking mode": "思考模式",
    "Send": "发送",
    "Insert code": "插入代码",
    "Copy": "复制",
    "Insert": "插入",
    "Notice": "提示",
    "Open a code file first.": "请先打开一个代码文件。",
    "Insert failed": "插入失败",
    "Could not locate the text cursor in the current editor.": (
        "无法定位当前编辑器的文本光标。"
    ),
    "Set API Key first": "请先设置 API Key",
    "Enter the API Key for the current provider in Settings.": (
        "请先在设置中填写当前供应商的 API Key。"
    ),
    "{provider}: syncing models...": "{provider}：正在同步模型...",
    "The provider returned an empty model list.": (
        "该供应商返回的模型列表为空。"
    ),
    "[API Key hidden]": "[API Key 已隐藏]",
    "Provider": "供应商",
    "{provider}: synced {count} models": (
        "{provider}：已同步 {count} 个模型"
    ),
    "Model list updated": "模型列表已更新",
    (
        "Provider: {provider}\nCurrent model: {model}\n"
        "{count} models available."
    ): (
        "供应商：{provider}\n当前模型：{model}\n"
        "共 {count} 个可用模型。"
    ),
    "Saved": "已保存",
    "{provider}: sync failed": "{provider}：同步失败",
    "Failed to fetch model list": "模型列表获取失败",
    "The plugin will keep the provider's cached model list.": (
        "插件将保留该供应商已有的模型缓存。"
    ),
    "Current provider": "当前供应商",
    (
        "⚠️ Click ⚙️ in the top-right corner to set the API base URL and "
        "API Key for “{provider}”."
    ): "⚠️ 请点击右上角 ⚙️ 设置“{provider}”的 API 地址和 API Key。",
    "Fetching provider models...": "正在获取供应商模型...",
    "Confirm": "确认",
    "Clear all chat history?": "确定要清空全部聊天记录吗？",
    "No provider": "没有供应商",
    "Configure a model provider in Settings first.": (
        "请先在设置中配置模型供应商。"
    ),
    "Set the API Key for “{provider}” first.": (
        "请先设置“{provider}”的 API Key。"
    ),
    "No model selected": "未选择模型",
    "Fetch and select a model for the current provider first.": (
        "请先获取并选择当前供应商的模型。"
    ),
    (
        "I am writing Python code in Thonny IDE. Analyze the following code "
        "and suggest improvements:"
    ): "我正在使用 Thonny IDE 编写 Python 代码，请分析下面的代码并给出修改建议：",
    "{provider} is thinking...": "{provider} 正在思考...",
    "Received only {count} characters of reasoning content": (
        "仅收到 {count} 字思考内容"
    ),
    "Finish reason: {reason}": "结束原因：{reason}",
    "No text content in the stream": "流中没有正文片段",
    "Thinking mode was enabled and was not turned off automatically.": (
        "思考模式已开启，未自动关闭"
    ),
    "Thinking mode was disabled according to the settings.": (
        "已按设置关闭思考模式"
    ),
    (
        "The current provider did not expose a recognizable parameter for "
        "disabling thinking mode."
    ): "当前供应商未提供可识别的思考模式关闭参数",
    (
        "The provider returned no text content ({details}). "
        "{thinking_status}; current output limit: {max_tokens} tokens."
    ): (
        "供应商未返回文本内容（{details}）。"
        "{thinking_status}；当前输出上限为 {max_tokens} tokens。"
    ),
    "The provider returned no text content.": "供应商未返回文本内容。",
    (
        "{provider} streaming request failed: {error}\n"
        "Check the API Key, account balance, model name, and network connection."
    ): (
        "{provider} 流式请求失败：{error}\n"
        "请检查 API Key、账户余额、模型名称和网络连接。"
    ),
    "👤 Me:": "👤 我：",
    "Analyze the selected code:": "请分析这段选中的代码：",
    "Analyze the complete code:": "请分析这段完整的代码：",
    "There is no code in the current editor to send.": (
        "当前编辑器中没有可发送的代码。"
    ),
    "Read failed": "读取失败",
    "Could not read the current code: {error}": "无法读取当前代码：{error}",
    "Analyze this code:": "请分析这段代码：",
    "Code analysis": "代码分析",
    "Send the code in the current editor to AI for analysis?": (
        "是否把当前编辑器中的代码发送给 AI 分析？"
    ),
    "Open AI Assistant from the View menu first.": (
        "请先从“视图”菜单打开 AI助手。"
    ),
}


def reset_language_cache():
    """Clear the cached language, mainly for tests and language changes."""
    global _UI_LANGUAGE
    _UI_LANGUAGE = None


def get_ui_language():
    """Return ``zh`` or ``en`` based on Thonny's configured UI language."""
    global _UI_LANGUAGE
    if _UI_LANGUAGE is None:
        try:
            language_code = str(
                get_workbench().get_option("general.language") or "en_US"
            )
        except Exception:
            return "en"
        _UI_LANGUAGE = (
            "zh" if language_code.lower().split("_", 1)[0] == "zh" else "en"
        )
    return _UI_LANGUAGE


def tr(message, **values):
    """Translate a UI message using named format values when provided."""
    translated = (
        _ZH_CN.get(message, message)
        if get_ui_language() == "zh"
        else message
    )
    return translated.format(**values) if values else translated
