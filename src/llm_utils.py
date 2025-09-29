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


def extract_requirements(rfp_text: str, attachments_text: str = "") -> Dict[str, Any]:
    """
    Extract requirements from RFP text using LLM.

    Args:
        rfp_text: Main RFP text
        attachments_text: Attachments text

    Returns:
        Dict with 'structured_attributes', 'requirements', 'critical_summary'
    """
    import re

    # DEBUG: Log input text
    print(f"DEBUG: RFP text length: {len(rfp_text)}")
    print(f"DEBUG: First 500 chars of RFP text: {rfp_text[:500]}")
    print(f"DEBUG: Attachments text length: {len(attachments_text)}")

    # Load prompt template
    prompt_file = "prompts/extract_requirements_prompt.txt"
    if not os.path.exists(prompt_file):
        raise FileNotFoundError(f"Prompt file not found: {prompt_file}")

    with open(prompt_file, 'r') as f:
        template = f.read()

    # Preprocessing: Find potential requirement sentences
    def find_potential_requirements(text: str) -> List[str]:
        """Find sentences that likely contain requirements."""
        # Split into sentences
        sentences = re.split(r'(?<=[.!?])\s+', text)

        # Keywords that indicate requirements
        req_keywords = [
            r'\bshall\b', r'\bmust\b', r'\bwill\b', r'\brequired\b', r'\bmandatory\b',
            r'\bshall not\b', r'\bmust not\b', r'\bwill not\b',
            r'\bcontractor shall\b', r'\bofferor shall\b', r'\bofferors shall\b',
            r'\bthe contractor\b.*\bshall\b', r'\bthe offeror\b.*\bshall\b'
        ]

        potential_reqs = []
        for sentence in sentences:
            sentence_lower = sentence.lower()
            if any(re.search(keyword, sentence_lower) for keyword in req_keywords):
                # Clean up the sentence
                clean_sentence = sentence.strip()
                if len(clean_sentence) > 20:  # Avoid very short fragments
                    potential_reqs.append(clean_sentence)

        return potential_reqs

    # Get potential requirements from both main text and attachments
    all_text = rfp_text + "\n\n" + attachments_text
    potential_reqs = find_potential_requirements(all_text)

    # Limit to top 100 most relevant potential requirements to avoid overwhelming the LLM
    # Prioritize sentences with stronger requirement language
    def score_requirement(sentence: str) -> int:
        score = 0
        lower = sentence.lower()
        if 'shall' in lower: score += 3
        if 'must' in lower: score += 3
        if 'required' in lower: score += 2
        if 'mandatory' in lower: score += 2
        if 'contractor shall' in lower: score += 2
        if 'offeror shall' in lower: score += 2
        if 'offerors shall' in lower: score += 2
        if 'will' in lower and 'shall' not in lower: score += 1  # Avoid false positives
        return score

    potential_reqs.sort(key=score_requirement, reverse=True)
    top_potential_reqs = potential_reqs[:100]  # Limit to avoid context overflow

    # Add the potential requirements to the prompt for better context
    potential_reqs_text = "\n".join(f"- {req}" for req in top_potential_reqs[:20])  # Show top 20 in prompt

    # Chunk the text to fit within LLM context (approx 3000 words per chunk for better performance)
    def chunk_text(text: str, chunk_size: int = 3000) -> List[str]:
        words = text.split()
        return [' '.join(words[i:i + chunk_size]) for i in range(0, len(words), chunk_size)]

    rfp_chunks = chunk_text(rfp_text)
    attachments_chunks = chunk_text(attachments_text) if attachments_text else []

    all_structured_attributes = {
        "client_company": {"content": "Not specified", "source_snippet": "", "page_number": 0, "section_title": ""},
        "department": {"content": "Not specified", "source_snippet": "", "page_number": 0, "section_title": ""},
        "project_background": {"content": "Not specified", "source_snippet": "", "page_number": 0, "section_title": ""},
        "objectives": {"content": "Not specified", "source_snippet": "", "page_number": 0, "section_title": ""},
        "scope": {"content": "Not specified", "source_snippet": "", "page_number": 0, "section_title": ""},
        "timeline": {"content": "Not specified", "source_snippet": "", "page_number": 0, "section_title": ""},
        "budget": {"content": "Not specified", "source_snippet": "", "page_number": 0, "section_title": ""},
        "evaluation_criteria": {"content": "Not specified", "source_snippet": "", "page_number": 0, "section_title": ""},
        "deliverables": {"content": "Not specified", "source_snippet": "", "page_number": 0, "section_title": ""},
        "bidder_requirements": {"content": "Not specified", "source_snippet": "", "page_number": 0, "section_title": ""},
        "compliance_items": {"content": "Not specified", "source_snippet": "", "page_number": 0, "section_title": ""},
        "risk_management": {"content": "Not specified", "source_snippet": "", "page_number": 0, "section_title": ""},
        "required_competencies": {"content": "Not specified", "source_snippet": "", "page_number": 0, "section_title": ""},
        "schedule": {"content": "Not specified", "source_snippet": "", "page_number": 0, "section_title": ""},
        "special_conditions": {"content": "Not specified", "source_snippet": "", "page_number": 0, "section_title": ""},
        "packaging_marking": {"content": "Not specified", "source_snippet": "", "page_number": 0, "section_title": ""},
        "inspection_acceptance": {"content": "Not specified", "source_snippet": "", "page_number": 0, "section_title": ""},
        "contract_admin_data": {"content": "Not specified", "source_snippet": "", "page_number": 0, "section_title": ""},
        "contract_clauses": {"content": "Not specified", "source_snippet": "", "page_number": 0, "section_title": ""},
        "representations": {"content": "Not specified", "source_snippet": "", "page_number": 0, "section_title": ""}
    }
    all_requirements = []
    all_critical_summaries = []

    for i, chunk in enumerate(rfp_chunks + attachments_chunks):
        # Fill template with potential requirements context
        prompt = template.replace("{{RFP_TEXT}}", chunk)
        prompt = prompt.replace("{{ATTACHMENTS_TEXT}}", attachments_text if i < len(rfp_chunks) else "")

        # Add potential requirements to help the LLM
        if potential_reqs_text:
            prompt += f"\n\nPOTENTIAL REQUIREMENTS FOUND IN TEXT:\n{potential_reqs_text}\n\nUse these as examples of the types of sentences to extract and format properly."

        # Call LLM
        response = call_ollama(prompt)

        # DEBUG: Log LLM response
        print(f"DEBUG: LLM response length: {len(response)}")
        print(f"DEBUG: First 1000 chars of LLM response: {response[:1000]}")

        try:
            # Clean response (remove markdown code blocks)
            response = response.strip()
            if response.startswith("```json"):
                response = response[7:]
            if response.endswith("```"):
                response = response[:-3]
            response = response.strip()

            data = json.loads(response)
            if isinstance(data, dict):
                # New hybrid format with structured_attributes, requirements, critical_summary
                if "structured_attributes" in data:
                    # Merge structured attributes (prefer first non-"Not specified")
                    for key, value in data["structured_attributes"].items():
                        if key not in all_structured_attributes or (
                            isinstance(all_structured_attributes.get(key), dict) and
                            all_structured_attributes[key].get("content") == "Not specified"
                        ):
                            all_structured_attributes[key] = value
                if "requirements" in data:
                    all_requirements.extend(data["requirements"])
                if "critical_summary" in data and "top_themes" in data["critical_summary"]:
                    all_critical_summaries.extend(data["critical_summary"]["top_themes"])
            else:
                print("Warning: Unexpected JSON structure")
        except json.JSONDecodeError as e:
            print(f"Failed to parse requirements JSON for chunk {i}: {e}")
            print(f"Cleaned response: {response[:500]}...")

            # Try to extract requirements from malformed JSON
            try:
                # Check if response contains multiple JSON objects separated by commas
                if '},{' in response:
                    # Split on '},{' and add back the braces
                    parts = response.split('},{')
                    for j, part in enumerate(parts):
                        if j == 0:
                            part = part + '}'
                        elif j == len(parts) - 1:
                            part = '{' + part
                        else:
                            part = '{' + part + '}'

                        try:
                            req_data = json.loads(part.strip())
                            if isinstance(req_data, dict) and 'req_id' in req_data:
                                # This is a proper requirement object
                                all_requirements.append(req_data)
                            elif isinstance(req_data, dict) and 'requirements' in req_data and isinstance(req_data['requirements'], list):
                                # This has a nested requirements array - extract individual requirements
                                for nested_req in req_data['requirements']:
                                    if isinstance(nested_req, dict) and 'req_id' in nested_req:
                                        all_requirements.append(nested_req)
                        except json.JSONDecodeError:
                            continue

                # If that doesn't work, try to find individual JSON objects
                import re
                json_pattern = r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}'
                matches = re.findall(json_pattern, response)
                for match in matches:
                    try:
                        req_data = json.loads(match)
                        if isinstance(req_data, dict) and 'req_id' in req_data:
                            # This is a proper requirement object
                            all_requirements.append(req_data)
                        elif isinstance(req_data, dict) and 'requirements' in req_data and isinstance(req_data['requirements'], list):
                            # This has a nested requirements array - extract individual requirements
                            for nested_req in req_data['requirements']:
                                if isinstance(nested_req, dict) and 'req_id' in nested_req:
                                    all_requirements.append(nested_req)
                    except json.JSONDecodeError:
                        continue

            except Exception as fallback_e:
                print(f"Fallback parsing also failed: {fallback_e}")
                continue

    # Remove duplicates based on req_id or description
    seen = set()
    unique_reqs = []
    for req in all_requirements:
        # Skip non-dict items that might have been added incorrectly
        if not isinstance(req, dict):
            continue
        key = (req.get('req_id'), req.get('description'))
        if key not in seen:
            seen.add(key)
            unique_reqs.append(req)

    # Sort by req_id to organize A-Z
    unique_reqs.sort(key=lambda x: x.get('req_id', ''))

    # Remove duplicates from critical summaries based on theme
    seen_themes = set()
    unique_themes = []
    for theme in all_critical_summaries:
        if theme.get('theme') not in seen_themes:
            seen_themes.add(theme.get('theme'))
            unique_themes.append(theme)

    return {
        "structured_attributes": all_structured_attributes,
        "requirements": unique_reqs,
        "critical_summary": {"top_themes": unique_themes}
    }
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

    result = extract_requirements(dummy_rfp)
    reqs = result.get('requirements', [])
    print(f"Extracted {len(reqs)} requirements")
    for req in reqs[:2]:  # Show first 2
        print(json.dumps(req, indent=2))