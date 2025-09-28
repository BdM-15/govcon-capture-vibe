"""
RFP Parser Module

Extracts text from RFP documents (PDF, Word, Excel) for processing.
Handles multiple file types and combines into single text string.
"""

import os
from typing import Dict, List, Optional
from pypdf import PdfReader
import docx
import openpyxl


def extract_text_from_pdf(file_path: str) -> str:
    """
    Extract text from PDF file.

    Args:
        file_path: Path to PDF file

    Returns:
        Extracted text as string
    """
    text = ""
    try:
        reader = PdfReader(file_path)
        for page in reader.pages:
            text += page.extract_text() + "\n"
    except Exception as e:
        print(f"Error reading PDF {file_path}: {e}")
    return text


def extract_text_from_docx(file_path: str) -> str:
    """
    Extract text from Word document.

    Args:
        file_path: Path to DOCX file

    Returns:
        Extracted text as string
    """
    text = ""
    try:
        doc = docx.Document(file_path)
        for para in doc.paragraphs:
            text += para.text + "\n"
    except Exception as e:
        print(f"Error reading DOCX {file_path}: {e}")
    return text


def extract_text_from_xlsx(file_path: str) -> str:
    """
    Extract text from Excel file.

    Args:
        file_path: Path to XLSX file

    Returns:
        Extracted text as string
    """
    text = ""
    try:
        wb = openpyxl.load_workbook(file_path)
        for sheet in wb.worksheets:
            for row in sheet.iter_rows(values_only=True):
                row_text = " ".join(str(cell) for cell in row if cell is not None)
                if row_text.strip():
                    text += row_text + "\n"
    except Exception as e:
        print(f"Error reading XLSX {file_path}: {e}")
    return text


def parse_rfp_documents(file_paths: List[str]) -> Dict[str, str]:
    """
    Parse multiple RFP documents and extract text.

    Args:
        file_paths: List of file paths to parse

    Returns:
        Dict with 'main_text' (combined text) and 'attachments' (by file)
    """
    main_text = ""
    attachments = {}

    for path in file_paths:
        if not os.path.exists(path):
            print(f"File not found: {path}")
            continue

        ext = os.path.splitext(path)[1].lower()
        if ext == '.pdf':
            text = extract_text_from_pdf(path)
        elif ext in ['.docx', '.doc']:
            text = extract_text_from_docx(path)
        elif ext in ['.xlsx', '.xls']:
            text = extract_text_from_xlsx(path)
        else:
            print(f"Unsupported file type: {ext}")
            continue

        # Assume first file is main RFP, others are attachments
        if not main_text:
            main_text = text
        else:
            attachments[os.path.basename(path)] = text

    combined_attachments = "\n\n".join([f"Attachment: {name}\n{content}" for name, content in attachments.items()])

    return {
        'main_text': main_text,
        'attachments_text': combined_attachments,
        'all_text': main_text + "\n\n" + combined_attachments
    }


# Example usage
if __name__ == "__main__":
    # Test with sample files (adjust paths as needed)
    sample_files = ["examples/sample_rfp.pdf"]  # Add real files later
    result = parse_rfp_documents(sample_files)
    print(f"Extracted {len(result['all_text'])} characters")