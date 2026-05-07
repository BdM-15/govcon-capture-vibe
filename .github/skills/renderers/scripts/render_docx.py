#!/usr/bin/env python3
"""Render a Markdown source into a Microsoft Word (.docx) file via Pandoc.

Phase 3d renderer for the proposal-generator skill. Federal proposals are
submitted as DOCX, often on agency- or company-mandated Word templates.
Pandoc's ``--reference-doc`` flag maps every Markdown heading/style onto the
template's corresponding Word style, which is the only practical way to honor
varied corporate templates without per-template rendering code.

Invocation contract (called via the skills runtime ``run_script`` tool):

    {
      "path": "scripts/render_docx.py",
      "args": [
        "--input",  "{artifacts}/proposal.md",
        "--output", "{artifacts}/proposal.docx",
        "--reference", "{skill_dir}/assets/reference.docx",  # optional
        "--toc"                                              # optional
      ],
      "timeout": 60
    }

Exits with code 0 on success and prints the absolute output path to stdout.
Exits non-zero with an actionable message on stderr if Pandoc is missing or
the conversion fails.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path
from xml.sax.saxutils import escape

PANDOC_INSTALL_HINT = (
    "Pandoc was not found on PATH. Used the built-in OpenXML fallback. "
    "Install Pandoc for template-aware DOCX rendering:\n"
    "  Windows : winget install --id JohnMacFarlane.Pandoc\n"
    "  macOS   : brew install pandoc\n"
    "  Linux   : apt install pandoc  (or your distro equivalent)\n"
    "See docs/PHASE_3D_TOOLCHAIN.md for details."
)


def _metadata_value(values: list[str], key: str, default: str = "") -> str:
    prefix = f"{key}="
    for value in values:
        if value.startswith(prefix):
            return value[len(prefix):].strip()
    return default


def _read_markdown(input_arg: str) -> str:
    if input_arg == "-":
        return sys.stdin.read()
    input_path = Path(input_arg).resolve()
    if not input_path.is_file():
        raise FileNotFoundError(f"Input markdown file not found: {input_path}")
    return input_path.read_text(encoding="utf-8")


def _run_text(text: str) -> str:
    return f'<w:r><w:t xml:space="preserve">{escape(text)}</w:t></w:r>'


def _paragraph(text: str, style: str | None = None) -> str:
    style_xml = f'<w:pPr><w:pStyle w:val="{style}"/></w:pPr>' if style else ""
    return f"<w:p>{style_xml}{_run_text(text)}</w:p>"


def _markdown_to_word_body(markdown: str, title: str) -> str:
    paragraphs: list[str] = []
    if title:
        paragraphs.append(_paragraph(title, "Title"))
    for raw_line in markdown.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        line = raw_line.rstrip()
        if not line.strip():
            continue
        stripped = line.lstrip()
        if stripped.startswith("### "):
            paragraphs.append(_paragraph(stripped[4:].strip(), "Heading3"))
        elif stripped.startswith("## "):
            paragraphs.append(_paragraph(stripped[3:].strip(), "Heading2"))
        elif stripped.startswith("# "):
            paragraphs.append(_paragraph(stripped[2:].strip(), "Heading1"))
        elif stripped.startswith(("- ", "* ")):
            paragraphs.append(_paragraph("• " + stripped[2:].strip(), "ListParagraph"))
        else:
            paragraphs.append(_paragraph(stripped))
    if not paragraphs:
        paragraphs.append(_paragraph("No content."))
    return "".join(paragraphs)


def _fallback_docx(markdown: str, output_path: Path, title: str) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    body = _markdown_to_word_body(markdown, title)
    created = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    document_xml = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:body>{body}<w:sectPr><w:pgSz w:w="12240" w:h="15840"/><w:pgMar w:top="1440" w:right="1440" w:bottom="1440" w:left="1440" w:header="720" w:footer="720" w:gutter="0"/></w:sectPr></w:body>
</w:document>
"""
    styles_xml = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:styles xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:style w:type="paragraph" w:default="1" w:styleId="Normal"><w:name w:val="Normal"/><w:qFormat/></w:style>
  <w:style w:type="paragraph" w:styleId="Title"><w:name w:val="Title"/><w:basedOn w:val="Normal"/><w:qFormat/><w:pPr><w:spacing w:after="240"/></w:pPr><w:rPr><w:b/><w:sz w:val="36"/></w:rPr></w:style>
  <w:style w:type="paragraph" w:styleId="Heading1"><w:name w:val="heading 1"/><w:basedOn w:val="Normal"/><w:qFormat/><w:pPr><w:spacing w:before="240" w:after="120"/></w:pPr><w:rPr><w:b/><w:sz w:val="28"/></w:rPr></w:style>
  <w:style w:type="paragraph" w:styleId="Heading2"><w:name w:val="heading 2"/><w:basedOn w:val="Normal"/><w:qFormat/><w:pPr><w:spacing w:before="200" w:after="100"/></w:pPr><w:rPr><w:b/><w:sz w:val="24"/></w:rPr></w:style>
  <w:style w:type="paragraph" w:styleId="Heading3"><w:name w:val="heading 3"/><w:basedOn w:val="Normal"/><w:qFormat/><w:pPr><w:spacing w:before="160" w:after="80"/></w:pPr><w:rPr><w:b/><w:sz w:val="22"/></w:rPr></w:style>
  <w:style w:type="paragraph" w:styleId="ListParagraph"><w:name w:val="List Paragraph"/><w:basedOn w:val="Normal"/><w:pPr><w:ind w:left="720" w:hanging="360"/></w:pPr></w:style>
</w:styles>
"""
    content_types = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
  <Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>
  <Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>
  <Override PartName="/docProps/app.xml" ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/>
</Types>
"""
    rels = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
  <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>
  <Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties" Target="docProps/app.xml"/>
</Relationships>
"""
    document_rels = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>
</Relationships>
"""
    core = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:dcterms="http://purl.org/dc/terms/" xmlns:dcmitype="http://purl.org/dc/dcmitype/" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
  <dc:title>{escape(title or "Theseus Skill Product")}</dc:title>
  <dc:creator>Project Theseus</dc:creator>
  <cp:lastModifiedBy>Project Theseus</cp:lastModifiedBy>
  <dcterms:created xsi:type="dcterms:W3CDTF">{created}</dcterms:created>
  <dcterms:modified xsi:type="dcterms:W3CDTF">{created}</dcterms:modified>
</cp:coreProperties>
"""
    app = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties" xmlns:vt="http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes">
  <Application>Project Theseus</Application>
</Properties>
"""
    with zipfile.ZipFile(output_path, "w", compression=zipfile.ZIP_DEFLATED) as docx:
        docx.writestr("[Content_Types].xml", content_types)
        docx.writestr("_rels/.rels", rels)
        docx.writestr("word/_rels/document.xml.rels", document_rels)
        docx.writestr("word/document.xml", document_xml)
        docx.writestr("word/styles.xml", styles_xml)
        docx.writestr("docProps/core.xml", core)
        docx.writestr("docProps/app.xml", app)


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="render_docx.py",
        description="Render Markdown to .docx via Pandoc (proposal-generator Phase 3d).",
    )
    p.add_argument(
        "--input",
        required=True,
        help="Path to the Markdown source file. Use '-' to read from stdin.",
    )
    p.add_argument(
        "--output",
        required=True,
        help="Path to write the .docx artifact (parent dir will be created).",
    )
    p.add_argument(
        "--reference",
        default=None,
        help="Optional Word template (.docx) whose styles will be inherited.",
    )
    p.add_argument(
        "--toc",
        action="store_true",
        help="Insert a table of contents at the top of the document.",
    )
    p.add_argument(
        "--metadata",
        action="append",
        default=[],
        metavar="KEY=VALUE",
        help="Pandoc metadata pair (repeatable), e.g. --metadata title='Volume I'.",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)

    pandoc = shutil.which("pandoc")
    if not pandoc:
        try:
            markdown = _read_markdown(args.input)
            output_path = Path(args.output).resolve()
            title = _metadata_value(args.metadata, "title", output_path.stem.replace("_", " ").title())
            _fallback_docx(markdown, output_path, title)
        except Exception as exc:  # noqa: BLE001
            print(str(exc), file=sys.stderr)
            return 2
        print(PANDOC_INSTALL_HINT, file=sys.stderr)
        print(str(output_path))
        return 0

    output_path = Path(args.output).resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    cmd: list[str] = [pandoc, "--from", "markdown", "--to", "docx", "-o", str(output_path)]

    if args.reference:
        ref_path = Path(args.reference).resolve()
        if not ref_path.is_file():
            print(
                f"Reference template not found: {ref_path}\n"
                "Continue without --reference to use Pandoc's default styles.",
                file=sys.stderr,
            )
            return 2
        cmd.extend(["--reference-doc", str(ref_path)])

    if args.toc:
        cmd.append("--toc")

    for kv in args.metadata:
        if "=" not in kv:
            print(f"Invalid --metadata value (expected KEY=VALUE): {kv}", file=sys.stderr)
            return 2
        cmd.extend(["--metadata", kv])

    if args.input == "-":
        stdin_text = sys.stdin.read()
        proc = subprocess.run(cmd, input=stdin_text, text=True, capture_output=True, check=False)
    else:
        input_path = Path(args.input).resolve()
        if not input_path.is_file():
            print(f"Input markdown file not found: {input_path}", file=sys.stderr)
            return 2
        cmd.append(str(input_path))
        proc = subprocess.run(cmd, text=True, capture_output=True, check=False)

    if proc.returncode != 0:
        # Pandoc writes diagnostics to stderr; surface them verbatim.
        sys.stderr.write(proc.stderr or "Pandoc exited non-zero with no stderr output.\n")
        return proc.returncode

    if not output_path.is_file():
        print(
            f"Pandoc reported success but output file is missing: {output_path}",
            file=sys.stderr,
        )
        return 1

    print(str(output_path))
    return 0


if __name__ == "__main__":
    sys.exit(main())
