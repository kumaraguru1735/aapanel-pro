import os
from . import register_tool
from .base import _xml_response

@register_tool(category="Agent", name_cn="Task Summary", risk_level="low")
def TaskSummary(content: str, **kwargs) -> str:
    """
    Save a final summary of the completed task. Call this at the very end of task execution.

    Include:
    - What was done (files created/modified, commands run)
    - Important notes or follow-up items
    - Markdown format preferred

    Args:
        content: Detailed task summary in markdown format
    """
    session_id = kwargs.get("session_id") or kwargs.get("parent_session_id")
    sessions_dir = kwargs.get("sessions_dir", "sessions")
    
    if not session_id:
        return _xml_response("TaskSummary", "error", "Session ID not found in context. This tool requires a session context.")
            
    return _xml_response("TaskSummary", "done", content)
