# -*- coding: utf-8 -*-
"""
GovCon-Capture-Vibe Streamlit App
Web interface for RFP analysis using LightRAG and structured extraction.
"""

import streamlit as st
import asyncio
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import List, Optional, Dict
import pandas as pd
import nest_asyncio

# Apply nest_asyncio to fix event loop conflicts in Streamlit
nest_asyncio.apply()

# Add src directory to Python path
sys.path.insert(0, str(Path(__file__).parent / "src"))

# Page config
st.set_page_config(
    page_title="GovCon-Capture-Vibe",
    page_icon="📋",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Initialize session state
if 'requirements' not in st.session_state:
    st.session_state.requirements = []
if 'structured_attributes' not in st.session_state:
    st.session_state.structured_attributes = {}
if 'critical_summary' not in st.session_state:
    st.session_state.critical_summary = {}
if 'processed_text' not in st.session_state:
    st.session_state.processed_text = ""

def display_requirements_table(requirements: List[Dict]):
    """Display requirements in a nice table format."""
    if not requirements:
        st.warning("No requirements extracted yet.")
        return
    
    # Convert to DataFrame for better display
    df = pd.DataFrame(requirements)
    
    # Configure column display
    st.dataframe(
        df,
        column_config={
            "id": st.column_config.TextColumn("ID", width="small"),
            "text": st.column_config.TextColumn("Requirement Text", width="large"),
            "type": st.column_config.TextColumn("Type", width="medium"),
            "compliance_level": st.column_config.TextColumn("Compliance", width="small"),
            "section": st.column_config.TextColumn("Section", width="small"),
            "source_paragraph": st.column_config.TextColumn("Reference", width="medium"),
        },
        use_container_width=True
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
    if not summary or not summary.get('themes'):
        st.warning("No critical themes identified yet.")
        return
    
    st.markdown("### Critical Themes")
    for theme in summary.get('themes', []):
        with st.expander(f"**{theme.get('theme', '')}** - {theme.get('importance', '')}"):
            st.write(f"**Key Requirements:** {', '.join(theme.get('key_reqs', []))}")
            st.write(f"**Summary:** {theme.get('summary', '')}")

async def process_rfp_files(uploaded_files) -> dict:
    """Process uploaded RFP files using LightRAG properly."""
    if not uploaded_files:
        return None
    
    try:
        # Import LightRAG at the function level to ensure proper environment
        import sys
        import os
        
        # Ensure we're using the right Python environment
        venv_path = os.path.join(os.getcwd(), '.venv', 'Lib', 'site-packages')
        if venv_path not in sys.path:
            sys.path.insert(0, venv_path)
        
        try:
            from lightrag import LightRAG, QueryParam
            from lightrag.llm.ollama import ollama_model_complete, ollama_embed
            from lightrag.utils import EmbeddingFunc
            from lightrag.kg.shared_storage import initialize_pipeline_status
        except ImportError as e:
            st.error(f"Failed to import LightRAG: {e}")
            st.error(f"Python path: {sys.path}")
            st.error(f"Current working directory: {os.getcwd()}")
            return None
        
        import tempfile
        
        # Extract and combine text from all uploaded files
        all_text = ""
        
        # Process each file
        for uploaded_file in uploaded_files:
            try:
                # Extract text based on file type
                file_extension = Path(uploaded_file.name).suffix.lower()
                text_content = ""
                
                if file_extension == '.txt':
                    # Handle text files with proper encoding
                    try:
                        text_content = uploaded_file.getvalue().decode('utf-8')
                    except UnicodeDecodeError:
                        try:
                            text_content = uploaded_file.getvalue().decode('latin1')
                        except:
                            text_content = uploaded_file.getvalue().decode('utf-8', errors='ignore')
                
                elif file_extension == '.pdf':
                    # Handle PDF files
                    import io
                    import pypdf
                    try:
                        pdf_file = io.BytesIO(uploaded_file.getvalue())
                        pdf_reader = pypdf.PdfReader(pdf_file)
                        text_pages = []
                        for page in pdf_reader.pages:
                            text_pages.append(page.extract_text())
                        text_content = "\n".join(text_pages)
                    except Exception as e:
                        st.warning(f"Could not extract text from PDF {uploaded_file.name}: {str(e)}")
                        continue
                
                elif file_extension in ['.docx', '.doc']:
                    # Handle Word documents
                    import io
                    from docx import Document
                    try:
                        doc_file = io.BytesIO(uploaded_file.getvalue())
                        doc = Document(doc_file)
                        text_paragraphs = []
                        for paragraph in doc.paragraphs:
                            text_paragraphs.append(paragraph.text)
                        text_content = "\n".join(text_paragraphs)
                    except Exception as e:
                        st.warning(f"Could not extract text from Word document {uploaded_file.name}: {str(e)}")
                        continue
                
                else:
                    st.warning(f"Unsupported file type: {uploaded_file.name}")
                    continue
                
                # Clean and validate extracted text
                if text_content and text_content.strip():
                    # Remove null bytes and clean text
                    clean_text = text_content.replace('\x00', '').strip()
                    if clean_text:
                        all_text += f"\n\n--- DOCUMENT: {uploaded_file.name} ---\n\n{clean_text}"
                    else:
                        st.warning(f"No readable text found in {uploaded_file.name}")
                else:
                    st.warning(f"No text content extracted from {uploaded_file.name}")
                    
            except Exception as e:
                st.warning(f"Error processing {uploaded_file.name}: {str(e)}")
                continue
        
        if not all_text.strip():
            st.error("No readable content extracted from uploaded files")
            return None
        
        st.success(f"Extracted {len(all_text)} characters for processing")
        
        # Create temporary working directory for LightRAG
        with tempfile.TemporaryDirectory() as temp_dir:
            # Initialize LightRAG instance
            with st.spinner("Initializing LightRAG..."):
                rag = LightRAG(
                    working_dir=temp_dir,
                    llm_model_func=ollama_model_complete,
                    llm_model_name=os.getenv("LLM_MODEL", "qwen2.5-coder:7b"),
                    summary_max_tokens=int(os.getenv("SUMMARY_MAX_TOKENS", "8192")),
                    chunk_token_size=int(os.getenv("CHUNK_TOKEN_SIZE", "2000")),
                    chunk_overlap_token_size=int(os.getenv("CHUNK_OVERLAP_TOKEN_SIZE", "200")),
                    llm_model_kwargs={
                        "host": os.getenv("LLM_BINDING_HOST", "http://localhost:11434"),
                        "options": {
                            "num_ctx": int(os.getenv("NUM_CTX", "32768")),
                            "num_predict": int(os.getenv("NUM_PREDICT", "4096")),
                            "temperature": float(os.getenv("LLM_TEMPERATURE", "0.1")),
                        },
                        "timeout": int(os.getenv("TIMEOUT", "600")),
                    },
                    embedding_func=EmbeddingFunc(
                        embedding_dim=int(os.getenv("EMBEDDING_DIM", "1024")),
                        max_token_size=int(os.getenv("MAX_EMBED_TOKENS", "8192")),
                        func=lambda texts: ollama_embed(
                            texts,
                            embed_model=os.getenv("EMBEDDING_MODEL", "bge-m3:latest"),
                            host=os.getenv("EMBEDDING_BINDING_HOST", "http://localhost:11434"),
                        ),
                    ),
                )
                
                # Initialize storage and pipeline
                await rag.initialize_storages()
                await initialize_pipeline_status()
            
            # Insert document into LightRAG
            with st.spinner("Indexing document with LightRAG..."):
                await rag.ainsert(all_text)
            
            # Query for requirements using LightRAG
            with st.spinner("Extracting requirements..."):
                requirements_response = await rag.aquery(
                    "Extract all requirements, specifications, and mandatory items from this RFP. List each requirement with its type, compliance level, and source section.",
                    param=QueryParam(mode="hybrid")
                )
            
            # Query for evaluation factors
            with st.spinner("Analyzing evaluation factors..."):
                eval_response = await rag.aquery(
                    "What are the evaluation factors and criteria used to assess proposals in this RFP?",
                    param=QueryParam(mode="hybrid")
                )
            
            # Query for key attributes
            with st.spinner("Extracting key attributes..."):
                attributes_response = await rag.aquery(
                    "What are the key attributes of this RFP including contract type, performance period, place of performance, and submission deadline?",
                    param=QueryParam(mode="global")
                )
            
            # Clean up LightRAG
            await rag.llm_response_cache.index_done_callback()
            await rag.finalize_storages()
        
        # Structure the responses for display
        requirements = []
        if requirements_response:
            # Parse requirements from response (simplified for demo)
            req_lines = requirements_response.split('\n')
            for i, line in enumerate(req_lines):
                if line.strip() and any(keyword in line.lower() for keyword in ['shall', 'must', 'will', 'require']):
                    requirements.append({
                        'id': f'REQ-{i+1:03d}',
                        'text': line.strip(),
                        'type': 'Functional' if 'function' in line.lower() else 'Technical',
                        'compliance_level': 'mandatory' if any(word in line.lower() for word in ['shall', 'must']) else 'optional',
                        'section': 'TBD',
                        'keywords': [word for word in line.split() if len(word) > 3][:5]
                    })
        
        # Create structured attributes
        structured_attributes = {
            "total_requirements": len(requirements),
            "document_length": len(all_text),
            "evaluation_factors": eval_response[:200] + "..." if eval_response and len(eval_response) > 200 else eval_response,
            "key_attributes": attributes_response[:200] + "..." if attributes_response and len(attributes_response) > 200 else attributes_response,
            "processing_status": "Complete"
        }
        
        # Create critical summary
        critical_summary = {
            "themes": [
                {
                    "theme": "Requirements Analysis",
                    "importance": "High",
                    "key_reqs": [req['id'] for req in requirements[:3]],
                    "summary": f"Extracted {len(requirements)} requirements using LightRAG hybrid search"
                },
                {
                    "theme": "Evaluation Criteria",
                    "importance": "High", 
                    "key_reqs": [],
                    "summary": eval_response[:100] + "..." if eval_response and len(eval_response) > 100 else eval_response or "No evaluation factors found"
                }
            ]
        }
        
        return {
            'requirements': requirements,
            'structured_attributes': structured_attributes,
            'critical_summary': critical_summary,
            'processed_text': all_text
        }
        
    except Exception as e:
        st.error(f"Processing failed: {str(e)}")
        import traceback
        st.error(f"Traceback: {traceback.format_exc()}")
        return None

def main():
    st.title("📋 GovCon-Capture-Vibe")
    st.subheader("Federal RFP Analysis Tool")
    
    st.markdown("""
    **Phase 1 Implementation:** Local RFP analysis using LightRAG and PydanticAI.
    Upload RFP documents to extract requirements and perform structured analysis.
    """)
    
    # Sidebar
    with st.sidebar:
        st.header("📁 Upload RFP Files")
        uploaded_files = st.file_uploader(
            "Choose RFP files",
            type=['txt', 'pdf', 'docx'],
            accept_multiple_files=True,
            help="Upload RFP documents (PDF, DOCX, or TXT)"
        )
        
        if st.button("🚀 Process Files", type="primary"):
            if uploaded_files:
                with st.spinner("Processing files with LightRAG pipeline..."):
                    result = asyncio.run(process_rfp_files(uploaded_files))
                    
                    if result:
                        st.session_state.requirements = result['requirements']
                        st.session_state.structured_attributes = result['structured_attributes']
                        st.session_state.critical_summary = result['critical_summary']
                        st.session_state.processed_text = result['processed_text']
                        st.success("✅ RFP processed successfully!")
            else:
                st.error("Please upload files first")
        
        st.markdown("---")
        st.markdown("### Instructions")
        st.markdown("""
        1. Upload RFP documents (PDF, DOCX, or TXT)
        2. Click 'Process Files' to analyze
        3. View results in the tabs below
        4. Use Q&A to query the documents
        """)
    
    # Main content tabs
    tab1, tab2, tab3, tab4 = st.tabs(["📊 Overview", "📋 Requirements", "💬 Ask Questions", "✅ Compliance"])
    
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
        if st.session_state.processed_text:
            question = st.text_input("Ask a question about the RFP:", 
                                    placeholder="What are the evaluation factors?")
            
            if st.button("🔍 Ask", type="primary") and question:
                # Simple text search for now - can be enhanced with RAG later
                with st.spinner("Searching..."):
                    text = st.session_state.processed_text.lower()
                    question_lower = question.lower()
                    
                    # Find relevant sections
                    lines = text.split('\n')
                    relevant_lines = [line for line in lines if any(word in line for word in question_lower.split())]
                    
                    if relevant_lines:
                        st.markdown("### Answer")
                        for line in relevant_lines[:5]:  # Show first 5 relevant lines
                            if line.strip():
                                st.write(f"• {line.strip()}")
                    else:
                        st.warning("No relevant information found for your question.")
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
                placeholder="Paste your proposal text for compliance checking..."
            )
            
            if st.button("📊 Assess Compliance", type="primary"):
                if proposal_file or proposal_text.strip():
                    proposal_content = ""
                    if proposal_file:
                        proposal_content = proposal_file.getvalue().decode('utf-8', errors='ignore')
                    else:
                        proposal_content = proposal_text
                    
                    with st.spinner("Assessing compliance..."):
                        # Simple compliance check
                        total_reqs = len(st.session_state.requirements)
                        mandatory_reqs = len([r for r in st.session_state.requirements if r.get('compliance_level') == 'mandatory'])
                        
                        # Check how many requirements have some mention in proposal
                        covered = 0
                        for req in st.session_state.requirements:
                            req_keywords = req.get('keywords', [])
                            if any(keyword.lower() in proposal_content.lower() for keyword in req_keywords):
                                covered += 1
                        
                        coverage_rate = (covered / total_reqs * 100) if total_reqs > 0 else 0
                        
                        st.success("Compliance assessment complete!")
                        
                        # Display summary
                        col1, col2, col3 = st.columns(3)
                        with col1:
                            st.metric("Coverage Rate", f"{coverage_rate:.1f}%")
                        with col2:
                            st.metric("Total Requirements", total_reqs)
                        with col3:
                            st.metric("Mandatory Requirements", mandatory_reqs)
                        
                        # Show detailed results
                        st.markdown("### Detailed Assessment")
                        for req in st.session_state.requirements:
                            req_keywords = req.get('keywords', [])
                            is_covered = any(keyword.lower() in proposal_content.lower() for keyword in req_keywords)
                            
                            status = "✅ Covered" if is_covered else "❌ Not Found"
                            with st.expander(f"{status} - {req.get('id', 'Unknown')}"):
                                st.write(f"**Requirement:** {req.get('text', 'N/A')}")
                                st.write(f"**Type:** {req.get('type', 'N/A')}")
                                st.write(f"**Keywords:** {', '.join(req_keywords)}")
                else:
                    st.error("Please provide proposal content")
        else:
            st.info("Upload and process RFP files first")

if __name__ == "__main__":
    main()