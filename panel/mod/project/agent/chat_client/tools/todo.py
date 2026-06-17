from typing import List, Dict, Any, Optional
import json
from . import register_tool
from .base import _xml_response

import json
import os
import time
from typing import List, Dict, Any, Optional
from enum import Enum


class TodoStatus(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class TodoPriority(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class TodoItem:
    def __init__(self, content: str, status: TodoStatus = TodoStatus.PENDING,
                 id: Optional[str] = None, priority: TodoPriority = TodoPriority.MEDIUM):
        self.id = id or str(int(time.time() * 1000))  # Simple ID generation
        self.content = content
        self.status = status
        self.priority = priority
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "content": self.content,
            "status": self.status,
            "priority": self.priority
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'TodoItem':
        return cls(
            content=data["content"],
            status=TodoStatus(data.get("status", "pending")),
            id=data.get("id"),
            priority=TodoPriority(data.get("priority", "medium"))
        )


class TodoManager:
    def __init__(self, session_id: str, sessions_dir: str = "sessions"):
        self.session_id = session_id
        self.session_dir = os.path.join(sessions_dir, session_id)
        self.file_path = os.path.join(self.session_dir, "todos.json")
        self._ensure_sessions_dir()
    
    def _ensure_sessions_dir(self):
        if not os.path.exists(self.session_dir):
            try:
                os.makedirs(self.session_dir)
            except OSError:
                pass
    
    def get_todos(self) -> List[TodoItem]:
        if not os.path.exists(self.file_path):
            return []
        
        try:
            with open(self.file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return [TodoItem.from_dict(item) for item in data]
        except Exception:
            return []
    
    def save_todos(self, todos: List[TodoItem]):
        data = [item.to_dict() for item in todos]
        try:
            with open(self.file_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception:
            pass
    
    def update_todos(self, new_todos_data: List[Dict[str, Any]], merge: bool = False) -> List[TodoItem]:
        if merge:
            current_todos = self.get_todos()
            current_map = {t.id: t for t in current_todos}
            
            for item_data in new_todos_data:
                item_id = item_data.get("id")
                if item_id and item_id in current_map:
                    # Update existing
                    existing = current_map[item_id]
                    existing.content = item_data.get("content", existing.content)
                    existing.status = TodoStatus(item_data.get("status", existing.status))
                    existing.priority = TodoPriority(item_data.get("priority", existing.priority))
                else:
                    # Add new
                    new_item = TodoItem.from_dict(item_data)
                    current_todos.append(new_item)
            
            final_todos = current_todos
        else:
            final_todos = [TodoItem.from_dict(item) for item in new_todos_data]
        
        self.save_todos(final_todos)
        return final_todos


# Load descriptions from files would be ideal, but for now we embed them or read them if possible.
# Since we are implementing them in python, we can just put the text in docstrings.

TODO_READ_DESC = """Use this tool to read the current to-do list.

Use proactively and frequently:
- At the start of a session to see what's pending
- Before starting new tasks to understand context
- When uncertain about what to do next
- After completing tasks to update your mental model
- Every few messages to stay on track

Returns a JSON list of todo items with id, content, status (pending/in_progress/completed/cancelled), and priority."""

TODO_WRITE_DESC = """Create and manage a structured task list for the current session.

When to use:
- Complex tasks with 3+ distinct steps
- User provides multiple tasks (numbered or comma-separated)
- After receiving new instructions — capture immediately as todos
- After completing a task — mark it done and add follow-ups

Task states:
- pending: Not yet started
- in_progress: Currently working on (limit to ONE at a time)
- completed: Finished successfully
- cancelled: No longer needed

Rules:
- Break complex tasks into small, actionable steps
- Only ONE task in_progress at any time
- Complete current tasks before starting new ones
- Mark tasks complete IMMEDIATELY after finishing (don't batch)
- Cancel irrelevant tasks"""

@register_tool(category="Agent", name_cn="TodoRead", risk_level="low")
def TodoRead(**kwargs) -> str:
    """
    Use this tool to read your todo list.
    """
    # Override docstring with full description
    TodoRead.__doc__ = TODO_READ_DESC
    
    session_id = kwargs.get("session_id") or kwargs.get("parent_session_id")
    sessions_dir = kwargs.get("sessions_dir", "sessions")
    if not session_id:
        return _xml_response("TodoRead", "error", "Session ID not found in context.")
        
    manager = TodoManager(session_id, sessions_dir=sessions_dir)
    todos = manager.get_todos()
    
    pending_count = len([t for t in todos if t.status != "completed"])
    
    output = {
        "title": f"{pending_count} todos",
        "output": json.dumps([t.to_dict() for t in todos], indent=2, ensure_ascii=False),
        "metadata": {
            "todos": [t.to_dict() for t in todos]
        }
    }
    
    # Return formatted string similar to other tools
    return _xml_response("TodoRead", "done", output['output'])

@register_tool(category="Agent", name_cn="TodoWrite", risk_level="low")
def TodoWrite(todos: List[Dict[str, Any]], merge: bool = False, summary: Optional[str] = None, **kwargs) -> str:
    """
    Use this tool to create and manage a structured task list for your current coding session.
    
    Args:
        todos: Array of todo items. Each item should have 'content', 'status' (pending/in_progress/completed), 'id', and 'priority'.
        merge: Whether to merge with existing todos.
        summary: Optional summary of work accomplished.
    """
    # Override docstring with full description
    TodoWrite.__doc__ = TODO_WRITE_DESC
    
    session_id = kwargs.get("session_id") or kwargs.get("parent_session_id")
    sessions_dir = kwargs.get("sessions_dir", "sessions")
    if not session_id:
        return _xml_response("TodoWrite", "error", "Session ID not found in context.")
        
    manager = TodoManager(session_id, sessions_dir=sessions_dir)
    updated_todos = manager.update_todos(todos, merge=merge)
    
    pending_count = len([t for t in updated_todos if t.status != "completed"])
    
    output = {
        "title": f"{pending_count} todos",
        "output": json.dumps([t.to_dict() for t in updated_todos], indent=2, ensure_ascii=False),
        "metadata": {
            "todos": [t.to_dict() for t in updated_todos]
        }
    }
    
    result_str = output['output']
        
    return _xml_response("TodoWrite", "done", result_str)
