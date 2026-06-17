from typing import Optional, Generator, Dict, Any
import json
import uuid
import os
from . import register_tool
from .base import _xml_response

from typing import List, Dict, Any, Optional
from dataclasses import dataclass

@dataclass
class AgentDefinition:
    name: str
    description: str
    allowed_tools: List[str]
    system_prompt_template: str

class AgentRegistry:
    def __init__(self):
        self._agents: Dict[str, AgentDefinition] = {}
        self._register_default_agents()

    def register(self, agent: AgentDefinition):
        self._agents[agent.name] = agent

    def get(self, name: str) -> Optional[AgentDefinition]:
        return self._agents.get(name)

    def list_agents(self) -> List[AgentDefinition]:
        return list(self._agents.values())

    def _register_default_agents(self):
        # Search Agent
        self.register(AgentDefinition(
            name="search",
            description="A specialist for searching the codebase and file system. Use this for exploration and information gathering.",
            allowed_tools=["Glob", "Grep", "LS", "Read", "RunCommand"],
            system_prompt_template="You are a search specialist. Your goal is to find information in the codebase efficiently. Use Glob and Grep tools to locate files and content. Use Read to inspect file contents. Do not modify files."
        ))

        # Planner Agent
        self.register(AgentDefinition(
            name="planner",
            description="A specialist for planning tasks and managing todo lists.",
            allowed_tools=["TodoWrite", "Read", "Task"],
            system_prompt_template="You are a planner. Your goal is to break down complex tasks into manageable steps. Use the TodoWrite tool to manage the task list. You can delegate subtasks to other agents using the Task tool."
        ))

        # Coder Agent
        self.register(AgentDefinition(
            name="coder",
            description="A specialist for writing and modifying code.",
            allowed_tools=["Glob", "Grep", "LS", "Read", "Write", "DeleteFile", "SearchReplace", "RunCommand", "Task"],
            system_prompt_template="You are a coding specialist. Your goal is to implement features and fix bugs. You can read and write files. You can also run commands to verify your work. If you need to search extensively, delegate to the search agent."
        ))

# Global registry instance
agent_registry = AgentRegistry()


@register_tool(category="Agent", name_cn="Task Sub-agent", risk_level="medium")
def Task(description: str, prompt: str, subagent_type: str, task_id: Optional[str] = None, **kwargs) -> str:
    """
    Launch a sub-agent to handle a complex task autonomously.

    Available subagent types:
    - search: Codebase exploration specialist (uses Glob, Grep, LS, Read, RunCommand)
    - planner: Task planning and todo management (uses TodoWrite, Read, Task)
    - coder: Code implementation specialist (uses all file and command tools)

    When to use:
    - Delegate broad, self-contained tasks that don't need your direct oversight
    - Parallelize independent work by launching multiple sub-agents
    - Complex exploration tasks (search agent)

    When NOT to use:
    - To read a specific file — use Read instead
    - To search for a class/function name — use Glob instead
    - To search within 2-3 known files — use Read instead

    Usage tips:
    - Launch multiple sub-agents in parallel (single message with multiple tool uses)
    - Be explicit about what information the agent should return in its final message
    - Each invocation starts fresh — provide detailed instructions in the prompt
    - Use task_id to resume a previous sub-agent session

    Args:
        description: Short task title (e.g., "Find all API endpoints")
        prompt: Detailed instructions for the sub-agent. Be specific about what to return.
        subagent_type: One of: "search", "planner", "coder"
        task_id: Optional session ID to resume a previous sub-agent conversation
    """
    
    # Deferred import to avoid circular dependency
    from ..agent import Agent

    # 1. Validate Agent Type
    agent_def = agent_registry.get(subagent_type)
    if not agent_def:
        available = [a.name for a in agent_registry.list_agents()]
        parent_session = kwargs.get("session_id")
        return _xml_response("Task", "error", f"Unknown agent type: '{subagent_type}'. Available agents: {', '.join(available)}")

    # 2. Session Management
    if task_id:
        session_id = task_id
    else:
        # Create new session ID
        session_id = str(uuid.uuid4())

    # 3. Configure Agent
    # We need to construct a config that enables the specific tools for this agent
    # and sets the system prompt.
    
    # Get current working directory
    cwd = os.getcwd()
    
    # Get parent config if available
    parent_config = kwargs.get("parent_config", {})
    parent_session_id = kwargs.get("parent_session_id")
    session_id_for_response = kwargs.get("session_id")
    
    # Start with default base config
    config = {
        "model_name": "gpt-4o", # Default
        "cwd": cwd,
        "code_mode": True, 
        "max_tool_iterations": 20
    }
    
    # Merge parent config (if any), but be careful not to overwrite critical agent-specific fields yet
    if parent_config:
        # Update config with parent config, but exclude 'tools' and 'system_prompt' which are specific to the subagent
        # We also want to preserve 'cwd' if parent has it
        for k, v in parent_config.items():
            if k not in ["tools", "system_prompt"]:
                config[k] = v
        
        # Determine sessions_dir
        # If we have a parent session, the sub-agent session should be stored inside it
        if parent_session_id:
            parent_sessions_dir = parent_config.get("sessions_dir", "sessions")
            # Structure: sessions/parent_id
            # The Agent class will append its session_id: sessions/parent_id/sub_id
            # So we set sessions_dir to: sessions/parent_id
            config["sessions_dir"] = os.path.join(parent_sessions_dir, parent_session_id)
    
    # Force agent-specific configuration
    config.update({
        "tools": agent_def.allowed_tools,
        "system_prompt": agent_def.system_prompt_template
    })

    # 4. Initialize Agent
    agent = Agent(session_id=session_id, config=config)
    
    try:
        # 5. Execute Agent Loop
        # Agent.chat is a generator. We need to consume it to let the agent run.
        # We collect the final response content.
        
        full_response = ""
        
        # Add a clear instruction to the prompt
        full_prompt = f"Task: {description}\n\nInstructions:\n{prompt}"
        
        generator = agent.chat(full_prompt)
        
        for chunk in generator:
            if chunk.get("type") == "content":
                full_response += chunk.get("response", "")
            elif chunk.get("type") == "error":
                return _xml_response("Task", "error", f"Agent error: {chunk.get('data')}")
                
        # 6. Return Result
        output = [
            f"task_id: {session_id}",
            "",
            "<task_result>",
            full_response,
            "</task_result>"
        ]
        
        return _xml_response("Task", "done", "\n".join(output))

    except Exception as e:
        return _xml_response("Task", "error", f"Task execution failed: {str(e)}")
    finally:
        # Clean up agent resources
        if hasattr(agent, "close"):
            agent.close()
