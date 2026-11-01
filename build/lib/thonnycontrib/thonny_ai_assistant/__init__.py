"""thonny-ai-assistant plugin."""

from thonny import get_workbench
from thonnycontrib.thonny_ai_assistant.i18n import tr
from thonnycontrib.thonny_ai_assistant.thonny_ai_assistant_tool import (
    AIChatView,
    thonny_ai_assistant,
)

def load_plugin():
    """Load plugin, register commands and toolbar buttons"""
    print("Loading thonny-ai-assistant plugin...")
    
    try:
        wb = get_workbench()
        
        wb.add_view(
            AIChatView,
            tr("AI Assistant"),
            "se",
            default_position_key="se"
        )
        
        # Register command (with concise description)
        wb.add_command(
            command_id="thonny_ai_assistant",
            menu_name="tools",
            command_label=tr("Open AI Assistant"),
            handler=thonny_ai_assistant,
            include_in_toolbar=True,  # Add to toolbar for quick access
            caption=tr("AI Assistant")
        )
        
        # Add API Key settings menu item
        wb.add_command(
            command_id="thonny_ai_assistant_settings",
            menu_name="tools",
            command_label=tr("AI Assistant Settings"),
            handler=lambda: AIChatView.show_api_key_dialog(),
            include_in_toolbar=False,
            caption=tr(
                "Manage AI providers, API endpoints, and API keys"
            )
        )
        
        print("thonny-ai-assistant plugin loaded successfully.")
    except Exception as e:
        print(f"Error loading thonny-ai-assistant plugin: {e}")
        import traceback
        traceback.print_exc()
