"""
GovCon-Capture-Vibe Streamlit App

Web interface for RFP analysis using LightRAG and Ollama.
"""

import streamlit as st
import asyncio
import json
import os
from typing import List, Optional
import pandas as pd
import nest_asyncio

# Apply nest_asyncio to fix event loop conflicts in Streamlit
nest_asyncio.apply()

# Import our modules
from src.rfp_parser import parse_rfp_documents
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
        # Parse documents
        with st.spinner("Parsing documents..."):
            parsed = parse_rfp_documents(temp_files)

        if not parsed['all_text'].strip():
            st.error("No text extracted from files")
            return None

        st.success(f"Extracted {len(parsed['all_text'])} characters")

        # Extract requirements
        with st.spinner("Extracting requirements..."):
            extraction_result = extract_requirements(parsed['main_text'], parsed['attachments_text'])
            requirements = extraction_result.get('requirements', [])
            structured_attributes = extraction_result.get('structured_attributes', {})
            critical_summary = extraction_result.get('critical_summary', {})

        st.success(f"Extracted {len(requirements)} requirements")

        # Initialize RAG
        with st.spinner("Setting up knowledge base..."):
            rag = await get_rfp_rag()
            await rag.index_rfp(parsed['all_text'])
            await rag.index_rfp(f"Extracted Requirements:\n{json.dumps(requirements)}")
            await rag.index_rfp(f"Structured Attributes:\n{json.dumps(structured_attributes)}")

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