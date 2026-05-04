"""GovCon prompt slices with a stable compatibility facade in prompts/govcon_prompt.py."""

from prompts.govcon.extraction import EXTRACTION_PROMPTS, build_v8_system_prompt
from prompts.govcon.query import QUERY_PROMPTS

__all__ = ["EXTRACTION_PROMPTS", "QUERY_PROMPTS", "build_v8_system_prompt"]

