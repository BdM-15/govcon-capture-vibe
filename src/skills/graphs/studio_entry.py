"""LangGraph Studio entrypoint for mission-readiness pipeline topology."""

from src.skills.graphs.langgraph_chain_runner import build_studio_graph

graph = build_studio_graph()