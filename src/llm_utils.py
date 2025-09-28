"""
LLM Utilities Module

Handles direct Ollama calls for prompt-based tasks like requirement extraction.
Complements LightRAG for structured outputs.
"""

import json
import ollama
from typing import Dict, Any, Optional, List
from dotenv import load_dotenv
import os

load_dotenv()


def call_ollama(prompt: str, model: str = None, **kwargs) -> str:
    """
    Call Ollama model with a prompt.

    Args:
        prompt: The prompt text
        model: Model name (defaults to LLM_MODEL env var)
        **kwargs: Additional Ollama parameters

    Returns:
        Model response as string
    """
    if model is None:
        model = os.getenv("LLM_MODEL", "qwen2.5-coder:7b")

    try:
        response = ollama.chat(
            model=model,
            messages=[{'role': 'user', 'content': prompt}],
            **kwargs
        )
        return response['message']['content']
    except Exception as e:
        print(f"Ollama call failed: {e}")
        return ""


def extract_requirements(rfp_text: str, attachments_text: str = "") -> list:
    """
    Extract requirements from RFP text using LLM.

    Args:
        rfp_text: Main RFP text
        attachments_text: Attachments text

    Returns:
        List of requirement dicts
    """
    # Load prompt template
    prompt_file = "prompts/extract_requirements_prompt.txt"
    if not os.path.exists(prompt_file):
        raise FileNotFoundError(f"Prompt file not found: {prompt_file}")

    with open(prompt_file, 'r') as f:
        template = f.read()

    # Chunk the text to fit within LLM context (approx 6000 words per chunk)
    def chunk_text(text: str, chunk_size: int = 6000) -> List[str]:
        words = text.split()
        return [' '.join(words[i:i + chunk_size]) for i in range(0, len(words), chunk_size)]

    rfp_chunks = chunk_text(rfp_text)
    attachments_chunks = chunk_text(attachments_text) if attachments_text else []

    all_requirements = []

    for i, chunk in enumerate(rfp_chunks + attachments_chunks):
        # Fill template
        prompt = template.replace("{{RFP_TEXT}}", chunk)
        prompt = prompt.replace("{{ATTACHMENTS_TEXT}}", attachments_text if i < len(rfp_chunks) else "")

        # Call LLM
        response = call_ollama(prompt)

        try:
            # Clean response (remove markdown code blocks)
            response = response.strip()
            if response.startswith("```json"):
                response = response[7:]
            if response.endswith("```"):
                response = response[:-3]
            response = response.strip()

            data = json.loads(response)
            if isinstance(data, dict) and "requirements" in data:
                # New format with requirements and critical_summary
                all_requirements.extend(data["requirements"])
            elif isinstance(data, list):
                # Old format, just the array
                all_requirements.extend(data)
            else:
                print("Warning: Unexpected JSON structure")
        except json.JSONDecodeError as e:
            print(f"Failed to parse requirements JSON for chunk {i}: {e}")
            print(f"Cleaned response: {response[:500]}...")

    # Remove duplicates based on req_id or description
    seen = set()
    unique_reqs = []
    for req in all_requirements:
        key = (req.get('req_id'), req.get('description'))
        if key not in seen:
            seen.add(key)
            unique_reqs.append(req)

    # Sort by req_id to organize A-Z
    unique_reqs.sort(key=lambda x: x.get('req_id', ''))

    return unique_reqs


def assess_compliance(extracted_reqs: list, proposal_text: str) -> list:
    """
    Assess proposal compliance against requirements.

    Args:
        extracted_reqs: List of requirement dicts
        proposal_text: Proposal text

    Returns:
        List of assessment dicts
    """
    prompt_file = "prompts/assess_compliance_prompt.txt"
    if not os.path.exists(prompt_file):
        raise FileNotFoundError(f"Prompt file not found: {prompt_file}")

    with open(prompt_file, 'r') as f:
        template = f.read()

    # Fill template
    prompt = template.replace("{{EXTRACTED_REQS_JSON}}", json.dumps(extracted_reqs))
    prompt = prompt.replace("{{PROPOSAL_TEXT}}", proposal_text)

    response = call_ollama(prompt)

    try:
        assessment = json.loads(response)
        return assessment
    except json.JSONDecodeError as e:
        print(f"Failed to parse compliance JSON: {e}")
        return []


# Example usage
if __name__ == "__main__":
    # Test with dummy data
    dummy_rfp = """
    Section A: Competition limited to EAGLE BOA holders.
    Section L: Technical Volume max 25 pages.
    Section M: Best value evaluation.
    """

    reqs = extract_requirements(dummy_rfp)
    print(f"Extracted {len(reqs)} requirements")
    for req in reqs[:2]:  # Show first 2
        print(json.dumps(req, indent=2))