"""契约 ⑭：角色助手（Agent Loop + 原子工具 + 确认卡与派单）。"""
from .hub import AgentHub
from .tools import TOOLS, ToolContext, openai_schemas

__all__ = ["AgentHub", "TOOLS", "ToolContext", "openai_schemas"]
