"""
GovCon-Capture-Vibe Streamlit App

Web interface for RFP analysis using LightRAG and Ollama.
"""

import streamlit as st
import asyncio
import json
import os
from typing import List, Optional, Dict
import pandas as pd
import nest_asyncio

# Apply nest_asyncio to fix event loop conflicts in Streamlit
nest_asyncio.apply()

# Import our modules
from src.rfp_rag import get_rfp_rag
from src.llm_utils import extract_requirements, assess_compliance

# Page config
st.set_page_config(
    page_title="GovCon-Capture-Vibe",
    page_icon="📋",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Initialize session state
if 'rag_instance' not in st.session_state:
    st.session_state.rag_instance = None
if 'requirements' not in st.session_state:
    st.session_state.requirements = None
if 'structured_attributes' not in st.session_state:
    st.session_state.structured_attributes = None
if 'critical_summary' not in st.session_state:
    st.session_state.critical_summary = None
if 'parsed_data' not in st.session_state:
    st.session_state.parsed_data = None

def display_requirements_table(requirements: List[dict]):
    """Display requirements in a nice table format."""
    if not requirements:
        st.warning("No requirements extracted yet.")
        return

    # Convert to DataFrame for better display
    df = pd.DataFrame(requirements)

    # Reorder columns for better display
    cols = ['req_id', 'section', 'description', 'compliance_type', 'rfp_ref']
    display_cols = [col for col in cols if col in df.columns]

    st.dataframe(
        df[display_cols],
        column_config={
            "req_id": st.column_config.TextColumn("ID", width="small"),
            "section": st.column_config.TextColumn("Section", width="medium"),
            "description": st.column_config.TextColumn("Description", width="large"),
            "compliance_type": st.column_config.TextColumn("Type", width="small"),
            "rfp_ref": st.column_config.TextColumn("Reference", width="medium"),
        }
    )

def display_structured_attributes(attributes: dict):
    """Display structured attributes in a nice format."""
    if not attributes:
        st.warning("No structured attributes extracted yet.")
        return

    st.markdown("### Key RFP Attributes")
    for key, value in attributes.items():
        if isinstance(value, dict) and 'content' in value:
            with st.expander(f"**{key.replace('_', ' ').title()}**"):
                st.write(f"**Content:** {value['content']}")
                if value.get('source_snippet'):
                    st.write(f"**Source:** {value['source_snippet'][:200]}...")
                if value.get('page_number'):
                    st.write(f"**Page:** {value['page_number']}")
                if value.get('section_title'):
                    st.write(f"**Section:** {value['section_title']}")
        else:
            st.write(f"**{key.replace('_', ' ').title()}:** {value}")

def display_critical_summary(summary: dict):
    """Display critical summary themes."""
    if not summary or not summary.get('top_themes'):
        return

    st.markdown("### Critical Themes")
    for theme in summary['top_themes']:
        with st.expander(f"**{theme.get('theme', 'Unknown')}** - {theme.get('importance', '')}"):
            st.write(f"**Key Requirements:** {', '.join(theme.get('key_reqs', []))}")
            st.write(f"**Summary:** {theme.get('summary', '')}")

async def process_rfp_files(uploaded_files) -> dict:
    """Process uploaded RFP files."""
    if not uploaded_files:
        return None

    # Save uploaded files temporarily
    temp_files = []
    for uploaded_file in uploaded_files:
        temp_path = f"temp_{uploaded_file.name}"
        with open(temp_path, "wb") as f:
            f.write(uploaded_file.getvalue())
        temp_files.append(temp_path)

    try:
        # Extract text from files
        with st.spinner("Extracting text from files..."):
            parsed = extract_text_from_files(temp_files)

        if not parsed['all_text'].strip():
            st.error("No text extracted from files")
            return None

        st.success(f"Extracted {len(parsed['all_text'])} characters")

        # Initialize RAG and index documents using native processing
        with st.spinner("Setting up knowledge base..."):
            rag = await get_rfp_rag()
            # Index the main document text using LightRAG's native processing
            track_id = await rag.index_rfp(parsed['all_text'], temp_files[0] if temp_files else None)

        # Extract requirements using the processed documents
        with st.spinner("Extracting requirements..."):
            # Get processed documents from LightRAG
            processed_docs = await rag.get_processed_documents(track_id)
            # Use the processed document content for requirement extraction
            doc_content = list(processed_docs.values())[0] if processed_docs else parsed['all_text']

            # Split content for main vs attachments (simple heuristic)
            main_content = doc_content
            attachments_content = ""
            if "ATTACHMENT" in doc_content.upper():
                parts = doc_content.upper().split("ATTACHMENT", 1)
                if len(parts) > 1:
                    main_content = parts[0]
                    attachments_content = "ATTACHMENT" + parts[1]

            extraction_result = extract_requirements(main_content, attachments_content)
            requirements = extraction_result.get('requirements', [])
            structured_attributes = extraction_result.get('structured_attributes', {})
            critical_summary = extraction_result.get('critical_summary', {})

        st.success(f"Extracted {len(requirements)} requirements")

        # Index extracted requirements into RAG for querying
        with st.spinner("Indexing requirements..."):
            reqs_text = f"Extracted Requirements:\n{json.dumps(requirements)}"
            await rag.index_rfp(reqs_text, "extracted_requirements.json")

            attrs_text = f"Structured Attributes:\n{json.dumps(structured_attributes)}"
            await rag.index_rfp(attrs_text, "structured_attributes.json")

        return {
            'parsed': parsed,
            'requirements': requirements,
            'structured_attributes': structured_attributes,
            'critical_summary': critical_summary,
            'rag': rag
        }

    finally:
        # Clean up temp files
        for temp_file in temp_files:
            if os.path.exists(temp_file):
                os.remove(temp_file)

async def query_rfp(question: str) -> str:
    """Query the RFP knowledge base."""
    if not st.session_state.rag_instance:
        st.error("Please upload and process RFP files first")
        return ""

    try:
        response = await st.session_state.rag_instance.query_rfp(question)
        return response
    except Exception as e:
        st.error(f"Query failed: {e}")
        return ""

def extract_text_from_files(file_paths: List[str]) -> Dict[str, str]:
    """
    Extract text from uploaded files.
    Note: PDF parsing is limited without PyMuPDF - using basic text extraction.

    Args:
        file_paths: List of file paths

    Returns:
        Dict with 'all_text', 'main_text', 'attachments_text'
    """
    all_text = ""
    main_text = ""
    attachments_text = ""

    for file_path in file_paths:
        file_ext = file_path.lower().split('.')[-1]

        try:
            if file_ext == 'pdf':
                # Basic PDF text extraction (limited)
                try:
                    import fitz  # PyMuPDF
                    doc = fitz.open(file_path)
                    text = ""
                    for page in doc:
                        text += page.get_text() + "\n"
                    doc.close()
                except ImportError:
                    # Fallback: try to read as text (won't work well for PDFs)
                    with open(file_path, 'rb') as f:
                        content = f.read()
                        text = content.decode('utf-8', errors='ignore')
                    print(f"Warning: PyMuPDF not available, PDF text extraction may be poor for {file_path}")
            elif file_ext in ['docx', 'doc']:
                try:
                    import docx
                    doc = docx.Document(file_path)
                    text = "\n".join([para.text for para in doc.paragraphs])
                except ImportError:
                    with open(file_path, 'rb') as f:
                        content = f.read()
                        text = content.decode('utf-8', errors='ignore')
                    print(f"Warning: python-docx not available, DOCX text extraction may be poor for {file_path}")
            elif file_ext in ['xlsx', 'xls']:
                try:
                    import openpyxl
                    wb = openpyxl.load_workbook(file_path)
                    text = ""
                    for sheet in wb.worksheets:
                        for row in sheet.iter_rows(values_only=True):
                            text += " ".join([str(cell) for cell in row if cell]) + "\n"
                except ImportError:
                    with open(file_path, 'rb') as f:
                        content = f.read()
                        text = content.decode('utf-8', errors='ignore')
                    print(f"Warning: openpyxl not available, Excel text extraction may be poor for {file_path}")
            else:
                # Try to read as plain text
                with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                    text = f.read()

            all_text += text + "\n\n"

            # Simple heuristic: if filename contains 'attachment' or similar, treat as attachment
            if any(keyword in file_path.lower() for keyword in ['attachment', 'att', 'j', 'appendix']):
                attachments_text += text + "\n\n"
            else:
                main_text += text + "\n\n"

        except Exception as e:
            print(f"Error extracting text from {file_path}: {e}")
            continue

    return {
        'all_text': all_text.strip(),
        'main_text': main_text.strip(),
        'attachments_text': attachments_text.strip()
    }

def main():
    st.title("📋 GovCon-Capture-Vibe")
    st.markdown("Local RFP Analysis Tool - Zero Cost, Full Privacy")

    # Sidebar
    with st.sidebar:
        st.header("📤 Upload RFP Files")
        uploaded_files = st.file_uploader(
            "Upload RFP documents (PDF, Word, Excel)",
            accept_multiple_files=True,
            type=['pdf', 'docx', 'doc', 'xlsx', 'xls']
        )

        if st.button("🔍 Process Files", type="primary"):
            if uploaded_files:
                result = asyncio.run(process_rfp_files(uploaded_files))
                if result:
                    st.session_state.parsed_data = result['parsed']
                    st.session_state.requirements = result['requirements']
                    st.session_state.structured_attributes = result['structured_attributes']
                    st.session_state.critical_summary = result['critical_summary']
                    st.session_state.rag_instance = result['rag']
                    st.success("✅ RFP processed successfully!")
            else:
                st.error("Please upload files first")

        st.markdown("---")
        st.markdown("### About")
        st.markdown("This tool extracts requirements from federal RFPs and provides AI-powered analysis using local models only.")

    # Main content
    tab1, tab2, tab3, tab4 = st.tabs(["� Overview", "�📋 Requirements", "💬 Ask Questions", "� Compliance Check"])

    with tab1:
        st.header("RFP Overview")
        col1, col2 = st.columns(2)

        with col1:
            if st.session_state.structured_attributes:
                display_structured_attributes(st.session_state.structured_attributes)
            else:
                st.info("Upload and process RFP files to see structured attributes")

        with col2:
            if st.session_state.critical_summary:
                display_critical_summary(st.session_state.critical_summary)
            else:
                st.info("Critical themes will appear here after processing")

    with tab2:
        st.header("Extracted Requirements")
        if st.session_state.requirements:
            display_requirements_table(st.session_state.requirements)

            # Download button
            req_json = json.dumps(st.session_state.requirements, indent=2)
            st.download_button(
                label="📥 Download Requirements JSON",
                data=req_json,
                file_name="extracted_requirements.json",
                mime="application/json"
            )
        else:
            st.info("Upload and process RFP files to see extracted requirements")

    with tab3:
        st.header("Ask the RFP")

        if st.session_state.rag_instance:
            question = st.text_input("Ask a question about the RFP:", placeholder="What are the evaluation factors?")

            if st.button("🔍 Ask", type="primary") and question:
                with st.spinner("Thinking..."):
                    answer = asyncio.run(query_rfp(question))

                if answer:
                    st.markdown("### Answer")
                    st.write(answer)
        else:
            st.info("Upload and process RFP files first")

    with tab4:
        st.header("Compliance Assessment")

        if st.session_state.requirements:
            st.markdown("Upload your proposal draft to check compliance:")

            proposal_file = st.file_uploader(
                "Upload proposal (PDF, Word, or paste text below)",
                type=['pdf', 'docx', 'doc', 'txt']
            )

            proposal_text = st.text_area(
                "Or paste proposal text here:",
                height=200,
                placeholder="Paste your proposal content here..."
            )

            if st.button("🔍 Assess Compliance", type="primary"):
                if proposal_file or proposal_text:
                    # Get proposal text
                    if proposal_file:
                        # Simple text extraction (could be enhanced)
                        proposal_content = proposal_file.getvalue().decode('utf-8', errors='ignore')
                    else:
                        proposal_content = proposal_text

                    with st.spinner("Assessing compliance..."):
                        assessment = assess_compliance(st.session_state.requirements, proposal_content)

                    if assessment:
                        st.success("Compliance assessment complete!")

                        # Display summary
                        if 'summary' in assessment[-1]:
                            summary = assessment[-1]['summary']
                            col1, col2, col3 = st.columns(3)
                            with col1:
                                st.metric("Compliance Rate", f"{summary.get('compliance_rate', 0)}%")
                            with col2:
                                st.metric("Total Requirements", summary.get('total_reqs', 0))
                            with col3:
                                st.metric("Critical Gaps", summary.get('critical_gaps', 0))

                        # Display detailed assessment
                        assessment_df = pd.DataFrame(assessment[:-1] if 'summary' in assessment[-1] else assessment)
                        st.dataframe(assessment_df)
                    else:
                        st.error("Assessment failed")
                else:
                    st.error("Please provide proposal content")
        else:
            st.info("Upload and process RFP files first")

if __name__ == "__main__":
    main()