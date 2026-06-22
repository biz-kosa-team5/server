from .comparison_tool import build_comparison_tool
from .legal_contract_tool import build_legal_contract_tool
from .price_trend_tool import build_price_trend_tool
from .recommendation_tool import build_recommendation_tool
from .simple_lookup_tool import build_simple_lookup_tool

def build_chatbot_tools(session):
  return [
    build_simple_lookup_tool(session),
    build_recommendation_tool(session),
    build_comparison_tool(session),
    build_price_trend_tool(session),
    build_legal_contract_tool(session),
  ]


__all__ = [
  "build_chatbot_tools",
  "build_comparison_tool",
  "build_legal_contract_tool",
  "build_price_trend_tool",
  "build_recommendation_tool",
  "build_simple_lookup_tool",
]
