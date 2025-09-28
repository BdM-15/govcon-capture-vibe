"""
RFP Processing Pipeline

Combines document parsing and RAG indexing for RFP analysis.
First step in the full pipeline: Extract -> Index -> Query.
"""

import asyncio
import json
from typing import List, Dict, Any
from src.rfp_rag import get_rfp_rag
from src.llm_utils import extract_requirements


def extract_text_from_files(file_paths: List[str]) -> Dict[str, str]:
    """
    Extract text from files (simplified version for pipeline).
    """
    all_text = ""
    main_text = ""
    attachments_text = ""

    for file_path in file_paths:
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                text = f.read()
            all_text += text + "\n\n"

            # Simple heuristic for attachments
            if any(keyword in file_path.lower() for keyword in ['attachment', 'att', 'j', 'appendix']):
                attachments_text += text + "\n\n"
            else:
                main_text += text + "\n\n"
        except Exception as e:
            print(f"Error reading {file_path}: {e}")

    return {
        'all_text': all_text.strip(),
        'main_text': main_text.strip(),
        'attachments_text': attachments_text.strip()
    }


async def process_rfp_files(file_paths: List[str]) -> Dict[str, Any]:
    """
    Process RFP files: extract text, extract requirements, index into RAG.

    Args:
        file_paths: List of RFP file paths

    Returns:
        Dict with processing results
    """
    # Step 1: Extract text from files
    print("Step 1: Extracting text from RFP files...")
    parsed = extract_text_from_files(file_paths)

    if not parsed['all_text'].strip():
        raise ValueError("No text extracted from files")

    print(f"Extracted {len(parsed['all_text'])} characters")

    # Step 2: Extract requirements
    print("Step 2: Extracting requirements...")
    requirements = extract_requirements(parsed['main_text'], parsed['attachments_text'])
    print(f"Extracted {len(requirements)} requirements")

    # Save requirements to file
    with open("extracted_requirements.json", "w") as f:
        json.dump(requirements, f, indent=2)
    print("Saved requirements to extracted_requirements.json")

    # Step 3: Index into RAG using native document processing
    print("Step 3: Indexing into RAG...")
    rag = await get_rfp_rag()

    # Index full text using LightRAG's native processing
    track_id = await rag.index_rfp(parsed['all_text'], file_paths[0] if file_paths else None)

    # Index requirements as structured data for specific queries
    reqs_text = json.dumps(requirements, indent=2)
    await rag.index_rfp(f"Extracted Requirements:\n{reqs_text}", "extracted_requirements.json")

    # Step 4: Test queries
    print("Step 4: Testing RAG queries...")
    test_queries = [
        "What are the key sections in this RFP?",
        "What are the compliance requirements?",
        "What is the proposal due date?"
    ]

    results = {}
    for query in test_queries:
        response = await rag.query_rfp(query)
        results[query] = response
        print(f"Q: {query}")
        print(f"A: {response[:150]}...")
        print()

    return {
        'parsed_data': parsed,
        'requirements': requirements,
        'rag_ready': True,
        'test_results': results
    }


async def query_rfp(question: str, mode: str = "hybrid") -> str:
    """
    Query the indexed RFP.

    Args:
        question: Question about the RFP
        mode: RAG query mode

    Returns:
        Response from RAG
    """
    rag = await get_rfp_rag()
    return await rag.query_rfp(question, mode)


# Example usage
async def main():
    # For now, use placeholder - replace with real RFP files
    sample_files = []  # Add "path/to/rfp.pdf" when available

    if sample_files:
        result = await process_rfp_files(sample_files)
        print("Processing complete!")
        print(f"Requirements extracted: {len(result['requirements'])}")
    else:
        print("No sample files provided. Testing with dummy data...")

        # Test with dummy text
        dummy_rfp = """
        Section A: Competition limited to EAGLE BOA holders under NAICS 561210.
        Section L: Technical Volume limited to 25 pages, 11 pt font, 1 inch margins.
        Section M: Best Value tradeoff among Technical, Past Performance, and Cost/Price.
        """

        print("Extracting requirements from dummy RFP...")
        reqs = extract_requirements(dummy_rfp)
        print(f"Extracted {len(reqs)} requirements")

        print("Indexing and testing RAG...")
        rag = await get_rfp_rag()
        await rag.index_rfp(dummy_rfp)
        await rag.index_rfp(f"Extracted Requirements:\n{json.dumps(reqs)}")

        response = await query_rfp("What are the evaluation factors?")
        print(f"RAG Response: {response}")


if __name__ == "__main__":
    asyncio.run(main())