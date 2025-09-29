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
    """Process uploaded RFP files using LightRAG's native document processing pipeline."""
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
        # Use LightRAG's native document processing approach
        with st.spinner("Processing documents with LightRAG pipeline..."):
            rag = await get_rfp_rag()
            
            # Extract text using LightRAG-compatible methods (no external PDF libraries)
            file_contents = []
            for temp_file in temp_files:
                try:
                    with open(temp_file, 'rb') as f:
                        raw_content = f.read()
                    
                    # Use LightRAG-style text extraction
                    if temp_file.lower().endswith('.pdf'):
                        # Basic PDF text extraction using regex patterns (LightRAG native compatible)
                        import re
                        
                        # Find text objects between BT (Begin Text) and ET (End Text) markers
                        text_objects = re.findall(rb'BT\s*(.*?)\s*ET', raw_content, re.DOTALL)
                        
                        extracted_texts = []
                        for obj in text_objects:
                            # Extract text within parentheses - this is how text is stored in PDFs
                            text_matches = re.findall(rb'\(([^)]*)\)', obj)
                            for match in text_matches:
                                try:
                                    # Decode and clean the text
                                    decoded_text = match.decode('utf-8', errors='ignore').strip()
                                    # Remove PDF-specific encoding artifacts
                                    decoded_text = re.sub(r'\\[0-9]{3}', '', decoded_text)  # Remove octal escapes
                                    decoded_text = decoded_text.replace('\\n', ' ').replace('\\r', ' ').replace('\\t', ' ')
                                    if decoded_text and len(decoded_text) > 3:  # Filter out very short fragments
                                        extracted_texts.append(decoded_text)
                                except:
                                    continue
                        
                        text = ' '.join(extracted_texts)
                        
                        # Fallback: try to find any readable text patterns if BT/ET extraction fails
                        if not text.strip():
                            # Look for readable ASCII sequences that might be text
                            readable_chunks = re.findall(rb'[A-Za-z0-9\s]{20,}', raw_content)
                            text = ' '.join(chunk.decode('ascii', errors='ignore').strip() for chunk in readable_chunks[:10])  # Limit to first 10 chunks
                            
                    else:
                        # For other file types, use UTF-8
                        text = raw_content.decode('utf-8', errors='ignore')
                    
                    if text.strip() and len(text.strip()) > 50:  # Only add substantial content
                        file_contents.append(text)
                        print(f"DEBUG: Extracted {len(text)} characters from {temp_file}")
                    else:
                        print(f"DEBUG: Insufficient content extracted from {temp_file}")
                        
                except Exception as e:
                    print(f"Error processing {temp_file}: {e}")
                    continue
            
            if not file_contents:
                st.error("Could not extract readable text from uploaded files")
                return None

            # Combine all extracted content
            combined_text = '\n\n'.join(file_contents)
            
            print(f"DEBUG: Combined text length: {len(combined_text)}")
            print(f"DEBUG: First 500 chars of combined text: {combined_text[:500]}")
            
            if len(combined_text.strip()) < 50:
                st.error("Extracted content is too short to process")
                return None

            st.success(f"Prepared {len(combined_text)} characters for LightRAG processing")

            # Use LightRAG's native document processing pipeline
            track_id = await rag.index_rfp(combined_text, temp_files[0] if temp_files else None)

        # Extract requirements using LightRAG-processed content
        with st.spinner("Extracting requirements from processed content..."):
            # Get content from LightRAG's processed documents
            processed_docs = await rag.get_processed_documents(track_id)
            
            if processed_docs:
                doc_content = list(processed_docs.values())[0]
            else:
                doc_content = combined_text

            # Split for main vs attachments
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

        # Index for querying
        with st.spinner("Indexing for Q&A..."):
            reqs_text = f"Extracted Requirements:\n{json.dumps(requirements)}"
            await rag.index_rfp(reqs_text, "extracted_requirements.json")

            attrs_text = f"Structured Attributes:\n{json.dumps(structured_attributes)}"
            await rag.index_rfp(attrs_text, "structured_attributes.json")

        return {
            'parsed': {'all_text': combined_text, 'main_text': main_content, 'attachments_text': attachments_content},
            'requirements': requirements,
            'structured_attributes': structured_attributes,
            'critical_summary': critical_summary,
            'rag': rag
        }

    finally:
        # Clean up
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