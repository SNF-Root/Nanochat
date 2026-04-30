# import re
# from typing import Optional, Dict
# from docling.document_converter import DocumentConverter, PdfFormatOption
# from docling.datamodel.pipeline_options import PdfPipelineOptions
# from docling.datamodel.base_models import InputFormat
# from models.insert import PromForm
# import os
# from multiprocessing import Pool
# import time
# from openai import AsyncOpenAI
# from typing import List
# from dataclasses import replace
# from database.pg import get_db_connection, init_prom_table
# import asyncio



# Maps numbered fields to their meaning
NUMERIC_FIELD_MAP = {
    # Matches the actual PROM form numbering (see e.g. ashutoshPROM.pdf)
    1: "The chemical or material",
    2: "Vendor/manufacturer info",
    3: "Reason for request",
    4: "Process Flow",
    5: "Amount and form",
    6: "Storage",
    7: "Disposal",
}

# Month name mapping for text-based dates
MONTH_MAP = {
    'january': 1, 'jan': 1,
    'february': 2, 'feb': 2,
    'march': 3, 'mar': 3,
    'april': 4, 'apr': 4,
    'may': 5,
    'june': 6, 'jun': 6,
    'july': 7, 'jul': 7,
    'august': 8, 'aug': 8,
    'september': 9, 'sep': 9, 'sept': 9,
    'october': 10, 'oct': 10,
    'november': 11, 'nov': 11,
    'december': 12, 'dec': 12,
}


def parse_date_from_text(text: str) -> Optional[str]:
    """Parse many common date formats and return MM/DD/YYYY."""
    if not text:
        return None

    # Remove label, ordinal suffixes, "of", abbreviation dots, and normalize whitespace
    cleaned = re.sub(r'(?i)\bDate\b\s*:?\s*', '', text)
    cleaned = re.sub(r'(\d{1,2})(st|nd|rd|th)\b', r'\1', cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r'\bof\b', ' ', cleaned, flags=re.IGNORECASE)
    cleaned = cleaned.replace(',', ' ')
    # Strip trailing dots from month abbreviations (e.g., "Oct." -> "Oct")
    cleaned = re.sub(r'([A-Za-z]{3,})\.', r'\1', cleaned)
    cleaned = re.sub(r'\s+', ' ', cleaned).strip()

    # 1) MM/DD/YYYY or MM-DD-YYYY or MM.DD.YYYY
    match = re.search(r'(\d{1,2})[\/\-.](\d{1,2})[\/\-.](\d{2,4})', cleaned)
    if match:
        m, d, y = int(match.group(1)), int(match.group(2)), match.group(3)
        if len(y) == 2:
            y = '20' + y
        return f"{m:02d}/{d:02d}/{y}"

    # 2) YYYY-MM-DD or YYYY/MM/DD or YYYY MM DD
    match = re.search(r'(\d{4})[\/\-.](\d{1,2})[\/\-.](\d{1,2})', cleaned)
    if match:
        y, m, d = match.group(1), int(match.group(2)), int(match.group(3))
        return f"{m:02d}/{d:02d}/{y}"

    match = re.search(r'(\d{4})\s+(\d{1,2})\s+(\d{1,2})', cleaned)
    if match:
        y, m, d = match.group(1), int(match.group(2)), int(match.group(3))
        return f"{m:02d}/{d:02d}/{y}"

    # 3) MM DD YYYY (space-separated)
    match = re.search(r'(\d{1,2})\s+(\d{1,2})\s+(\d{2,4})', cleaned)
    if match:
        m, d, y = int(match.group(1)), int(match.group(2)), match.group(3)
        if len(y) == 2:
            y = '20' + y
        return f"{m:02d}/{d:02d}/{y}"

    # 4) D Month YYYY (e.g., 4 June 2019)
    match = re.search(r'(\d{1,2})\s+([A-Za-z]+)\s+(\d{2,4})', cleaned)
    if match:
        d = int(match.group(1))
        month_name = match.group(2).lower()
        y = match.group(3)
        if len(y) == 2:
            y = '20' + y
        if month_name in MONTH_MAP:
            m = MONTH_MAP[month_name]
            return f"{m:02d}/{d:02d}/{y}"

    # 5) Month D YYYY (e.g., June 4 2019)
    match = re.search(r'([A-Za-z]+)\s+(\d{1,2})\s+(\d{2,4})', cleaned)
    if match:
        month_name = match.group(1).lower()
        d = int(match.group(2))
        y = match.group(3)
        if len(y) == 2:
            y = '20' + y
        if month_name in MONTH_MAP:
            m = MONTH_MAP[month_name]
            return f"{m:02d}/{d:02d}/{y}"

    # 6) DMonYYYY or DDMonYYYY (e.g., 2Oct2019, 15Jan2020)
    match = re.search(r'(\d{1,2})([A-Za-z]+)(\d{2,4})', cleaned)
    if match:
        d = int(match.group(1))
        month_name = match.group(2).lower()
        y = match.group(3)
        if len(y) == 2:
            y = '20' + y
        if month_name in MONTH_MAP:
            m = MONTH_MAP[month_name]
            return f"{m:02d}/{d:02d}/{y}"

    # 7) MonDDYYYY (e.g., Oct22019, Jan152020) — month-first compact
    match = re.search(r'([A-Za-z]+)(\d{1,2})(\d{4})', cleaned)
    if match:
        month_name = match.group(1).lower()
        d = int(match.group(2))
        y = match.group(3)
        if month_name in MONTH_MAP:
            m = MONTH_MAP[month_name]
            return f"{m:02d}/{d:02d}/{y}"

    # 8) DD/Mon/YYYY or DD-Mon-YYYY (e.g., 02/Oct/2019, 2-Oct-2019)
    match = re.search(r'(\d{1,2})[\/\-.]([A-Za-z]+)[\/\-.](\d{2,4})', cleaned)
    if match:
        d = int(match.group(1))
        month_name = match.group(2).lower()
        y = match.group(3)
        if len(y) == 2:
            y = '20' + y
        if month_name in MONTH_MAP:
            m = MONTH_MAP[month_name]
            return f"{m:02d}/{d:02d}/{y}"

    # 9) Mon/DD/YYYY or Mon-DD-YYYY (e.g., Oct/02/2019, Oct-2-2019)
    match = re.search(r'([A-Za-z]+)[\/\-.](\d{1,2})[\/\-.](\d{2,4})', cleaned)
    if match:
        month_name = match.group(1).lower()
        d = int(match.group(2))
        y = match.group(3)
        if len(y) == 2:
            y = '20' + y
        if month_name in MONTH_MAP:
            m = MONTH_MAP[month_name]
            return f"{m:02d}/{d:02d}/{y}"

    # 10) Month YYYY only — no day (e.g., October 2019) — default to 1st
    match = re.search(r'([A-Za-z]+)\s+(\d{4})', cleaned)
    if match:
        month_name = match.group(1).lower()
        y = match.group(2)
        if month_name in MONTH_MAP:
            m = MONTH_MAP[month_name]
            return f"{m:02d}/01/{y}"

    return None



BULLET_PATTERN = re.compile(r'^[\s\-\u2022\u2023\u25E6\u2043\u2219\u00B7\u25AA\u25CF\u25CB\u2013\u2014\*\>]+')

def strip_bullets(text: str) -> str:
    """Strip leading bullet points, dashes, and list markers from text."""
    return BULLET_PATTERN.sub('', text).strip()


client = AsyncOpenAI(
    api_key=os.environ.get("STANFORD_API_KEY"),
    base_url=os.environ.get("STANFORD_BASE_URL", "https://aiapi-prod.stanford.edu/v1")
)


MAX_CONCURRENT_PROM_REQUESTS = 20


BOILERPLATE_PATTERNS = [
    # Chemical/Material section boilerplate - stop at specific phrases
    r"Please provide all common names,?\s*trade names,?\s*and CAS numbers.*?Main Hazard Class of your chemical/material\.?",
    r"Please provide all common names,?\s*trade names,?\s*and CAS numbers.*?chemical/material\.?",
    r"Please provide all common names,?\s*trade names,?\s*and CAS numbers.*?Storage Group Identifier[^.]*\.?",
    r"Please provide all common names.*?Read the MSDSs as well as the",
    r"Please provide all common names.*?secondary chemicals[^.]*\.",
    r"Include an MSDS,? if available[^.]*\.",
    r"Make sure to include information for any new secondary chemicals[^.]*\.",
    r"Read the MSDSs as well as the",
    
    # Vendor info boilerplate
    r"Vendor/manufacturer info:?\s*address and phone number,?\s*website URL\.?",
    r"address and phone number,?\s*website URL\.?",
    
    # Reason for request boilerplate
    r"Please give serious thought to this\..*?Will any of the current SNF approved chemicals and materials work for me\?",
    r"Please give serious thought to this\..*?work for me\?",
    r"Please give serious thought to this\..*?newer/safer alternatives[^?]*\?",
    
    # Process Flow boilerplate
    r"Please provide a detailed process flow description.*?MOS grade or better\.?\s*",
    r"Please provide a detailed process flow description.*?better\.?\s*",
    r"Please provide a detailed process flow description.*?wet benches\.?",
    r"Please provide a detailed process flow description.*?clean.*?tool[^.]*\.",
    r"all Lab equipment to be used for processing[^.]*\.",
    r"Make sure to include wet benches\.?",
    r"Please note that.*?the material should MOS grade or better\.?\s*",
    
    # Amount and form boilerplate
    r"How much will you bring in\?.*?Do you need to mix it to use it\?",
    r"How much will you bring in\?.*?mix it to use it\?",
    r"How much will you bring in\?.*?powders are not permitted[^.]*\.",
    r"Is it solid,? powder or liquid\?[^.]*\.?",
    
    # Storage boilerplate
    r"Will you be storing your chemical/material at SNF\?.*?at any wet bench\.?\s*",
    r"Will you be storing your chemical/material at SNF\?.*?wet bench\.?\s*",
    r"Will you be storing your chemical/material at SNF\?.*?bulk storage area\.?",
    r"Storage groups? A,? B,? D and L are stored[^.]*\.",
    r"Ensure your chemical container or material is properly labeled\.?",
    
    # Disposal boilerplate
    r"How will you dispose of any waste.*?available in the lab\.?\s*",
    r"How will you dispose of any waste.*?the lab\.?\s*",
    r"How will you dispose of any waste.*?Safety Manual[^.]*\.",
    r"for the different methods of waste disposal[^.]*\.",
    
    # Stanford Chemical Storage Groups reference (specific phrase, not open-ended)
    r"Stanford Chemical Storage Groups\s*to determine[^.]*\.",
    r"to determine the Storage Group Identifier[^.]*\.",
]


def strip_boilerplate(content: str) -> str:
    """
    Remove boilerplate instructional text from field content.
    Keeps the actual user-provided content that comes after the boilerplate.
    """
    if not content:
        return content
    
    # Normalize whitespace FIRST so patterns can match consistently
    result = re.sub(r'\s+', ' ', content).strip()
    
    for pattern in BOILERPLATE_PATTERNS:
        # Use IGNORECASE for flexibility (DOTALL not needed after whitespace normalization)
        result = re.sub(pattern, '', result, flags=re.IGNORECASE)
    
    # Clean up any resulting whitespace issues
    result = re.sub(r'\s+', ' ', result).strip()
    
    return result


def build_embed_string(prom_form: PromForm) -> str:
    """Build the string to be embedded from PromForm fields."""
    parts = []
    
    if prom_form.request_title:
        parts.append(f"Request Title: {prom_form.request_title}")
    
    if prom_form.chemicals_and_processes:
        parts.append(f"Chemical or Material: {prom_form.chemicals_and_processes}")
    
    if prom_form.request_reason:
        parts.append(f"Reason for Request: {prom_form.request_reason[:600]}")

    
    return "\n".join(parts)


def get_charspan_length(text_item: dict) -> int:
    """Get character span length from text item."""
    try:
        charspan = text_item.get('prov', [{}])[0].get('charspan', [0, 0])
        return charspan[1] - charspan[0]
    except:
        return 0


def extract_prom_from_docling(file_path: str, debug: bool = False) -> Optional[PromForm]:
    """
    Extract PROM form data using docling's structured JSON output.
    Supports both PDF and DOCX files.
    Much cleaner than regex on raw text.
    
    Args:
        file_path: Path to the PDF or DOCX file
        debug: If True, print extracted text items for debugging
    """
    # Configure PDF-specific options
    pipeline_options = PdfPipelineOptions(do_ocr=False)
    pdf_format_option = PdfFormatOption(pipeline_options=pipeline_options)
    
    # Create converter that supports both PDF and DOCX
    converter = DocumentConverter(
        allowed_formats=[InputFormat.PDF, InputFormat.DOCX],
        format_options={InputFormat.PDF: pdf_format_option}
    )
    
    try:
        result = converter.convert(file_path)
        doc_json = result.document.export_to_dict()
    except Exception as e:
        print(f"Error converting document {file_path}: {e}")
        return None
    
    texts = doc_json.get("texts", [])
    if not texts:
        return None
    
    # Debug: print all text items
    if debug:
        print(f"\n--- DEBUG: Text items from {file_path} ---")
        for i, item in enumerate(texts):
            text = item.get('text', '').replace('\t', ' ').strip()[:100]  # First 100 chars
            print(f"  [{i}] {repr(text)}")
        print("--- END DEBUG ---\n")
    
    # Storage for extracted data
    title = None
    requestor = None
    date = None
    email = None
    numbered_fields = {}  # 1-7 mapped fields
    staff_considerations = None
    
    # Build raw text for storage
    raw_text_parts = []
    
    # Helper to check if content is just a label (not actual user content)
    def is_just_label(content: str) -> bool:
        """Check if content is just a field label, not actual user-provided content."""
        if not content:
            return True
        content_lower = content.lower().strip().rstrip(':').rstrip('.')
        for label in NUMERIC_FIELD_MAP.values():
            if content_lower == label.lower() or content_lower == label.lower().rstrip(':'):
                return True
        return False
    
    # Helper to get next meaningful  text item
    def get_next_content(idx: int) -> Optional[str]:
        """Get the next text item's content if it exists and is meaningful."""
        if idx + 1 < len(texts):
            next_item = texts[idx + 1]
            next_text = next_item.get('text', '').replace('\t', ' ').strip()
            # Skip if it's another label or too short
            if next_text and not is_just_label(next_text) and len(next_text) > 3:
                return next_text
        return None
    
    # === PASS 1: Find section boundaries and extract header info ===
    section_starts = []  # List of (index, section_num)
    
    for idx, item in enumerate(texts):
        text = item.get('text', '').replace('\t', ' ').strip()
        charspan_len = get_charspan_length(item)
        
        # Skip very short items (just markers, page numbers, etc.)
        if charspan_len < 3:
            continue
        
        raw_text_parts.append(text)
        
        # Check for section markers (1-7)
        section_num = None
        
        # Method 1: Check enumerated marker from docling metadata
        if item.get('enumerated') and item.get('marker'):
            marker = item.get('marker', '').strip()
            num_match = re.match(r'(\d+)\.', marker)
            if num_match:
                num = int(num_match.group(1))
                if 1 <= num <= 7:
                    # Only mark as section start if not already found
                    if not any(s[1] == num for s in section_starts):
                        section_num = num
        
        # Method 2: Check if text starts with number pattern
        if section_num is None:
            num_match = re.match(r'^(\d+)\.\s*(.+)', text)
            if num_match:
                num = int(num_match.group(1))
                if 1 <= num <= 7:
                    if not any(s[1] == num for s in section_starts):
                        section_num = num
        
        # Method 3: Check for label text (strip leading bullets/markers)
        if section_num is None:
            text_lower = strip_bullets(text).lower()
            for num, label in NUMERIC_FIELD_MAP.items():
                if not any(s[1] == num for s in section_starts):
                    if text_lower.startswith(label.lower()) or label.lower() + ':' in text_lower:
                        section_num = num
                        break
        
        if section_num is not None:
            section_starts.append((idx, section_num))
    
    # Sort by index to ensure proper order
    section_starts.sort(key=lambda x: x[0])
    
    # === PASS 2: Aggregate content between section boundaries ===
    for i, (start_idx, section_num) in enumerate(section_starts):
        # Find end index (start of next section or end of texts)
        if i + 1 < len(section_starts):
            end_idx = section_starts[i + 1][0]
        else:
            end_idx = len(texts)
        
        # Gather all text items between start and end
        content_parts = []
        for j in range(start_idx, end_idx):
            item_text = texts[j].get('text', '').replace('\t', ' ').strip()
            if item_text and len(item_text) > 1:
                # NOTE: Do NOT stop on nested numbered lists (e.g., "1. Run ..." inside Process Flow).
                # We already bound the section by (start_idx, end_idx) using section_starts.
                content_parts.append(item_text)
        
        if content_parts:
            full_content = ' '.join(content_parts)
            numbered_fields[section_num] = strip_boilerplate(full_content)
    
    # === PASS 3: Extract header fields (Title, Requestor, Date, Email) ===
    for idx, item in enumerate(texts):
        text = strip_bullets(item.get('text', '').replace('\t', ' ').strip())
        
        # Title field
        if text.startswith('Title:') or 'Title:' in text[:20]:
            title_match = re.search(r'Title:\s*(.+?)(?:\s*Request|$)', text, re.IGNORECASE)
            if title_match:
                title = title_match.group(1).strip()
        
        # Requestor field - look for standalone "Requestor:" followed by name
        if 'Requestor:' in text:
            # If text is just "Requestor:", the name is in the next item
            if text.strip() == 'Requestor:':
                # Will be handled by next item
                pass
            else:
                # Stop at "Date:" if both are on same line
                req_match = re.search(r'Requestor:\s*(.+?)(?:\s+Date:|\s*$)', text, re.IGNORECASE)
                if req_match:
                    requestor = req_match.group(1).strip()
        
    # Date field - can be standalone or on same line as Requestor
        if re.search(r'\bdate\b', text, re.IGNORECASE):
            parsed_date = parse_date_from_text(text)
            if parsed_date:
                date = parsed_date
        
        # Email/Badger ID field
        if 'Badger' in text or 'Email:' in text:
            email_match = re.search(r'([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})', text)
            if email_match:
                email = email_match.group(1).lower()
        
        # Staff considerations (after "To be completed by PROM COMMITTEE")
        if 'Special handling' in text:
            staff_considerations = text
    
    # Handle case where Requestor name is in a separate text item
    # Look for name after "Requestor:" item
    for i, item in enumerate(texts):
        text = strip_bullets(item.get('text', '').replace('\t', ' ').strip())
        if text == 'Requestor:' and i + 1 < len(texts):
            next_text = texts[i + 1].get('text', '').replace('\t', ' ').strip()
            # Make sure it's not another label
            if not any(label in next_text for label in ['Date:', 'Email:', 'Badger', 'Title:']):
                requestor = next_text
                break
    
    # Handle case where Date is in a separate text item
    # Look for date after "Date:" / "Date" item
    if not date:
        for i, item in enumerate(texts):
            text = strip_bullets(item.get('text', '').replace('\t', ' ').strip())
            if re.match(r'^date\s*:?\s*$', text, re.IGNORECASE) and i + 1 < len(texts):
                next_text = texts[i + 1].get('text', '').replace('\t', ' ').strip()
                parsed_next = parse_date_from_text(next_text)
                if parsed_next:
                    date = parsed_next
                    break
    
    # Validation
    if not date:
        print(f"Could not find date in {file_path}")
        return None
    
    requestor_id = email or requestor
    if not requestor_id:
        print(f"Could not find requestor in {file_path}")
        return None
    
    # Build PromForm
    prom_form = PromForm(
        date=date,
        filename=file_path,
        requestor=requestor_id,
        request_title=title,
        chemicals_and_processes=numbered_fields.get(1),  # 1. Chemical/material
        # PROM numbering: 2=vendor (ignored), 3=reason, 4=process flow, 5=amount/form
        request_reason=numbered_fields.get(3),           # 3. Reason for request
        process_flow=numbered_fields.get(4),             # 4. Process flow
        amount_and_form=numbered_fields.get(5),          # 5. Amount and form
        staff_considerations=staff_considerations,
        raw_prom="\n".join(raw_text_parts),
    )
    
    return prom_form


def extract_prom_from_docx(file_path: str, debug: bool = False) -> Optional[PromForm]:
    """
    DOCX-specific extraction that handles:
    - Requestor and Date on same line
    - Section labels without number prefixes
    - Content spanning multiple text items
    - Fragmented text aggregation
    """
    # Create converter for DOCX
    converter = DocumentConverter(allowed_formats=[InputFormat.DOCX])
    
    try:
        result = converter.convert(file_path)
        doc_json = result.document.export_to_dict()
    except Exception as e:
        print(f"Error converting DOCX {file_path}: {e}")
        return None
    
    texts = doc_json.get("texts", [])
    if not texts:
        return None
    
    # Extract text content from all items
    text_items = []
    for item in texts:
        text = item.get('text', '').replace('\t', ' ').strip()
        text_items.append(text)
    
    if debug:
        print(f"\n--- DEBUG: Text items from {file_path} ---")
        for i, text in enumerate(text_items):
            print(f"  [{i}] {repr(text[:100])}")
        print("--- END DEBUG ---\n")
    
    # Section markers (lowercase for matching)
    SECTION_LABELS = {
        # Match actual PROM numbering for clarity; we still skip vendor in the final PromForm.
        "the chemical or material": 1,
        "vendor/manufacturer info": 2,
        "reason for request": 3,
        "process flow": 4,
        "amount and form": 5,
        "storage": 6,
        "disposal": 7,
        "to be completed by": None,  # End marker
        "special handling": None,  # Staff section
    }
    
    # Storage
    title = None
    requestor = None
    date = None
    email = None
    sections = {}  # field_num -> list of text items
    staff_considerations = None
    raw_text_parts = []
    
    # Helper to get next non-empty text item
    def get_next_text(idx: int) -> Optional[str]:
        """Get the next non-empty text item."""
        for j in range(idx + 1, min(idx + 3, len(text_items))):
            if text_items[j] and len(text_items[j].strip()) > 2:
                return text_items[j].strip()
        return None
    
    # First, find header info (Title, Requestor, Date, Email)
    for i, text in enumerate(text_items):
        if not text:
            continue
        raw_text_parts.append(text)
        # Strip leading bullets/markers for field detection
        text = strip_bullets(text)
        
        # Request Title - check same line OR next line
        if 'request title:' in text.lower():
            match = re.search(r'Request Title:\s*(.+)', text, re.IGNORECASE)
            if match:
                extracted = match.group(1).strip()
                # If extracted is empty or just whitespace, look at next line
                if not extracted or len(extracted) < 2:
                    next_text = get_next_text(i)
                    if next_text:
                        title = next_text
                else:
                    title = extracted
            else:
                # Label only, content on next line
                next_text = get_next_text(i)
                if next_text:
                    title = next_text
        
        # Requestor and Date - might be on same line!
        if 'requestor:' in text.lower():
            # Check if Date is on same line
            if re.search(r'\bdate\b', text, re.IGNORECASE):
                # Combined line: "Requestor: Name      Date: MM/DD/YYYY"
                req_match = re.search(r'Requestor:\s*(.+?)\s+Date\b', text, re.IGNORECASE)
                if req_match:
                    requestor = req_match.group(1).strip()
                # Extract date from same line in any common format
                parsed_date = parse_date_from_text(text)
                if parsed_date:
                    date = parsed_date
            else:
                # Requestor only on this line - check if content follows or is on next line
                req_match = re.search(r'Requestor:\s*(.+)', text, re.IGNORECASE)
                if req_match:
                    extracted = req_match.group(1).strip()
                    if not extracted or len(extracted) < 2:
                        # Look at next line
                        next_text = get_next_text(i)
                        if next_text and not re.search(r'\bdate\b', next_text, re.IGNORECASE):
                            requestor = next_text
                    else:
                        requestor = extracted
                else:
                    # Just "Requestor:" label, content on next line
                    next_text = get_next_text(i)
                    if next_text and not re.search(r'\bdate\b', next_text, re.IGNORECASE):
                        requestor = next_text
        
        # Date on its own line (if not found above)
        if not date and re.search(r'\bdate\b', text, re.IGNORECASE) and 'requestor:' not in text.lower():
            parsed_date = parse_date_from_text(text)
            if parsed_date:
                date = parsed_date
            else:
                # Date label only, date value on next line
                next_text = get_next_text(i)
                parsed_next = parse_date_from_text(next_text)
                if parsed_next:
                    date = parsed_next
        
        # Badger ID / Email
        if 'badger' in text.lower() or 'email' in text.lower():
            # Try to find email first
            email_match = re.search(r'([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})', text)
            if email_match:
                email = email_match.group(1).lower()
            else:
                # Try to extract Badger ID/username from same line
                badger_match = re.search(r'Badger\s*ID:\s*(\w+)', text, re.IGNORECASE)
                if badger_match:
                    # Use username as identifier (append @stanford.edu if needed)
                    username = badger_match.group(1).strip()
                    if username and not email:
                        email = username  # Store username as requestor identifier
                else:
                    # Check next line for email or username
                    next_text = get_next_text(i)
                    if next_text:
                        email_match = re.search(r'([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})', next_text)
                        if email_match:
                            email = email_match.group(1).lower()
                        elif not email:
                            # Next line might just be a username
                            username_match = re.match(r'^(\w+)(?:,|\s|$)', next_text.strip())
                            if username_match:
                                email = username_match.group(1).strip()
    
    # Find section boundaries
    # Must be strict to avoid false matches like "Stanford Chemical Storage Groups" matching "storage"
    section_starts = []  # List of (index, field_num, label)
    for i, text in enumerate(text_items):
        # Strip leading bullets/markers before matching
        text_stripped = strip_bullets(text)
        
        # Strip leading numbered prefix (e.g., "3. Reason for request" -> "Reason for request")
        # Don't trust docling's marker numbers — they restart from 1 in each list context
        num_match = re.match(r'^(\d+)\.\s*(.*)', text_stripped)
        if num_match:
            text_stripped = num_match.group(2).strip()
        
        # Label text matching
        text_lower = text_stripped.lower()
        text_cleaned = text_lower.rstrip(':').rstrip('.')
        
        for label, field_num in SECTION_LABELS.items():
            # Strict matching: text must START with label or BE the label (with punctuation)
            is_match = False
            
            # Exact match (with or without trailing punctuation)
            if text_cleaned == label:
                is_match = True
            # Starts with label followed by colon or period (strong signals)
            elif text_lower.startswith(label + ':') or text_lower.startswith(label + '.'):
                is_match = True
            # Short text that starts with label (avoid matching long content lines
            # like "Storage group D or F..." against the "storage" label)
            # Cap at label + 30 to allow annotations like "Process Flow (and safety concern)"
            elif len(text_cleaned) < len(label) + 30 and text_cleaned.startswith(label):
                is_match = True
            
            if is_match:
                section_starts.append((i, field_num, label))
                break
    
    # Sort by index
    section_starts.sort(key=lambda x: x[0])
    
    # Aggregate content for each section
    for idx, (start_idx, field_num, label) in enumerate(section_starts):
        if field_num is None:
            continue  # Skip non-numbered sections
        
        # Find end index (start of next section or end of list)
        if idx + 1 < len(section_starts):
            end_idx = section_starts[idx + 1][0]
        else:
            end_idx = len(text_items)
        
        # Gather all text items between start and end
        content_parts = []
        
        # Check if the label line itself has inline content (e.g., "Reason for request: actual content here")
        label_text = strip_bullets(text_items[start_idx])
        # Strip numbered prefix
        label_num_match = re.match(r'^(\d+)\.\s*(.*)', label_text)
        if label_num_match:
            label_text = label_num_match.group(2).strip()
        # Try to extract content after the label
        for lbl in list(SECTION_LABELS.keys()) + [v.lower() for v in NUMERIC_FIELD_MAP.values()]:
            inline_match = re.match(r'(?i)' + re.escape(lbl) + r'[\s.:]*(.+)', label_text)
            if inline_match:
                inline_content = inline_match.group(1).strip()
                if inline_content and len(inline_content) > 3:
                    content_parts.append(inline_content)
                break
        
        for j in range(start_idx + 1, end_idx):  # Remaining items after the label
            text = text_items[j]
            if text and len(text) > 1:  # Skip empty and single-char items (superscripts)
                # Skip if it's another section label
                text_stripped = strip_bullets(text)
                stripped_num = re.match(r'^(\d+)\.\s*(.*)', text_stripped)
                if stripped_num:
                    text_stripped = stripped_num.group(2).strip()
                text_lower = text_stripped.lower().rstrip(':').rstrip('.')
                # Only skip if the text IS a section label (exact match or starts with label)
                # NOT a substring match — content like "...for disposal." should not be skipped
                is_label = any(
                    text_lower == lbl or text_lower.startswith(lbl + ':') or text_lower.startswith(lbl + '.')
                    for lbl in SECTION_LABELS.keys()
                )
                if not is_label:
                    content_parts.append(text)
        
        if content_parts:
            sections[field_num] = ' '.join(content_parts)
    
    # Extract staff considerations
    for i, text in enumerate(text_items):
        if 'special handling' in text.lower():
            # Gather content after this
            staff_parts = []
            for j in range(i + 1, min(i + 5, len(text_items))):
                if text_items[j]:
                    staff_parts.append(text_items[j])
            if staff_parts:
                staff_considerations = ' '.join(staff_parts)
            break
    
    # Validation
    if not date:
        print(f"Could not find date in {file_path}")
        return None
    
    requestor_id = email or requestor
    if not requestor_id:
        print(f"Could not find requestor in {file_path}")
        return None
    
    # Apply boilerplate stripping to sections
    for field_num in sections:
        sections[field_num] = strip_boilerplate(sections[field_num])
    
    # Build PromForm
    prom_form = PromForm(
        date=date,
        filename=file_path,
        requestor=requestor_id,
        request_title=title,
        chemicals_and_processes=sections.get(1),
        request_reason=sections.get(3),
        process_flow=sections.get(4),
        amount_and_form=sections.get(5),
        staff_considerations=staff_considerations,
        raw_prom="\n".join(raw_text_parts),
    )
    
    return prom_form


def extract_prom_unified(file_path: str, debug: bool = False) -> Optional[PromForm]:
    """
    Unified extraction that handles both PDF and DOCX files.
    Uses the robust DOCX-specific logic (strict label matching, inline content
    extraction, multi-step Badger ID fallback, multi-line staff considerations)
    applied to docling's structured JSON output for any supported format.

    This replaces both extract_prom_from_docling (PDF) and extract_prom_from_docx
    (DOCX) with a single code path. The two original functions are preserved
    above so we can revert if needed.
    """
    # Configure PDF-specific options (no OCR needed)
    pipeline_options = PdfPipelineOptions(do_ocr=False)
    pdf_format_option = PdfFormatOption(pipeline_options=pipeline_options)

    # Create converter that supports both PDF and DOCX
    converter = DocumentConverter(
        allowed_formats=[InputFormat.PDF, InputFormat.DOCX],
        format_options={InputFormat.PDF: pdf_format_option}
    )

    try:
        result = converter.convert(file_path)
        doc_json = result.document.export_to_dict()
    except Exception as e:
        print(f"Error converting document {file_path}: {e}")
        return None

    texts = doc_json.get("texts", [])
    if not texts:
        return None

    # Extract text content from all items
    text_items = []
    for item in texts:
        text = item.get('text', '').replace('\t', ' ').strip()
        text_items.append(text)

    if debug:
        print(f"\n--- DEBUG: Text items from {file_path} ---")
        for i, text in enumerate(text_items):
            print(f"  [{i}] {repr(text[:100])}")
        print("--- END DEBUG ---\n")

    # Section markers (lowercase for matching)
    SECTION_LABELS = {
        "the chemical or material": 1,
        "vendor/manufacturer info": 2,
        "reason for request": 3,
        "process flow": 4,
        "amount and form": 5,
        "storage": 6,
        "disposal": 7,
        "to be completed by": None,  # End marker
        "special handling": None,  # Staff section
    }

    # Storage
    title = None
    requestor = None
    date = None
    email = None
    sections = {}  # field_num -> list of text items
    staff_considerations = None
    raw_text_parts = []

    # Helper to get next non-empty text item
    def get_next_text(idx: int) -> Optional[str]:
        """Get the next non-empty text item."""
        for j in range(idx + 1, min(idx + 3, len(text_items))):
            if text_items[j] and len(text_items[j].strip()) > 2:
                return text_items[j].strip()
        return None

    # First, find header info (Title, Requestor, Date, Email)
    for i, text in enumerate(text_items):
        if not text:
            continue
        raw_text_parts.append(text)
        # Strip leading bullets/markers for field detection
        text = strip_bullets(text)

        # Request Title - check same line OR next line
        if 'request title:' in text.lower() or 'title:' in text.lower()[:20]:
            match = re.search(r'(?:Request\s+)?Title:\s*(.+)', text, re.IGNORECASE)
            if match:
                extracted = match.group(1).strip()
                # If extracted is empty or just whitespace, look at next line
                if not extracted or len(extracted) < 2:
                    next_text = get_next_text(i)
                    if next_text:
                        title = next_text
                else:
                    title = extracted
            else:
                # Label only, content on next line
                next_text = get_next_text(i)
                if next_text:
                    title = next_text

        # Requestor and Date - might be on same line!
        if 'requestor:' in text.lower():
            # Check if Date is on same line
            if re.search(r'\bdate\b', text, re.IGNORECASE):
                # Combined line: "Requestor: Name      Date: MM/DD/YYYY"
                req_match = re.search(r'Requestor:\s*(.+?)\s+Date\b', text, re.IGNORECASE)
                if req_match:
                    requestor = req_match.group(1).strip()
                # Extract date from same line in any common format
                parsed_date = parse_date_from_text(text)
                if parsed_date:
                    date = parsed_date
            else:
                # Requestor only on this line - check if content follows or is on next line
                req_match = re.search(r'Requestor:\s*(.+)', text, re.IGNORECASE)
                if req_match:
                    extracted = req_match.group(1).strip()
                    if not extracted or len(extracted) < 2:
                        # Look at next line
                        next_text = get_next_text(i)
                        if next_text and not re.search(r'\bdate\b', next_text, re.IGNORECASE):
                            requestor = next_text
                    else:
                        requestor = extracted
                else:
                    # Just "Requestor:" label, content on next line
                    next_text = get_next_text(i)
                    if next_text and not re.search(r'\bdate\b', next_text, re.IGNORECASE):
                        requestor = next_text

        # Date on its own line (if not found above)
        if not date and re.search(r'\bdate\b', text, re.IGNORECASE) and 'requestor:' not in text.lower():
            parsed_date = parse_date_from_text(text)
            if parsed_date:
                date = parsed_date
            else:
                # Date label only, date value on next line
                next_text = get_next_text(i)
                if next_text:
                    parsed_next = parse_date_from_text(next_text)
                    if parsed_next:
                        date = parsed_next

        # Badger ID / Email — multi-step fallback
        if 'badger' in text.lower() or 'email' in text.lower():
            # Try to find email first
            email_match = re.search(r'([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})', text)
            if email_match:
                email = email_match.group(1).lower()
            else:
                # Try to extract Badger ID/username from same line
                badger_match = re.search(r'Badger\s*ID:\s*(\w+)', text, re.IGNORECASE)
                if badger_match:
                    username = badger_match.group(1).strip()
                    if username and not email:
                        email = username
                else:
                    # Check next line for email or username
                    next_text = get_next_text(i)
                    if next_text:
                        email_match = re.search(r'([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})', next_text)
                        if email_match:
                            email = email_match.group(1).lower()
                        elif not email:
                            username_match = re.match(r'^(\w+)(?:,|\s|$)', next_text.strip())
                            if username_match:
                                email = username_match.group(1).strip()

    # Find section boundaries
    # Strict matching to avoid false positives like "Stanford Chemical Storage Groups" matching "storage"
    section_starts = []  # List of (index, field_num, label)
    for i, text in enumerate(text_items):
        # Strip leading bullets/markers before matching
        text_stripped = strip_bullets(text)

        # Strip leading numbered prefix (e.g., "3. Reason for request" -> "Reason for request")
        # Don't trust docling's marker numbers — they restart from 1 in each list context
        num_match = re.match(r'^(\d+)\.\s*(.*)', text_stripped)
        if num_match:
            text_stripped = num_match.group(2).strip()

        # Label text matching
        text_lower = text_stripped.lower()
        text_cleaned = text_lower.rstrip(':').rstrip('.')

        for label, field_num in SECTION_LABELS.items():
            is_match = False

            # Exact match (with or without trailing punctuation)
            if text_cleaned == label:
                is_match = True
            # Starts with label followed by colon or period (strong signals)
            elif text_lower.startswith(label + ':') or text_lower.startswith(label + '.'):
                is_match = True
            # Short text that starts with label (avoid matching long content lines)
            # Cap at label + 30 to allow annotations like "Process Flow (and safety concern)"
            elif len(text_cleaned) < len(label) + 30 and text_cleaned.startswith(label):
                is_match = True

            if is_match:
                section_starts.append((i, field_num, label))
                break

    # Sort by index
    section_starts.sort(key=lambda x: x[0])

    # Aggregate content for each section
    for idx, (start_idx, field_num, label) in enumerate(section_starts):
        if field_num is None:
            continue  # Skip non-numbered sections

        # Find end index (start of next section or end of list)
        if idx + 1 < len(section_starts):
            end_idx = section_starts[idx + 1][0]
        else:
            end_idx = len(text_items)

        # Gather all text items between start and end
        content_parts = []

        # Check if the label line itself has inline content
        label_text = strip_bullets(text_items[start_idx])
        # Strip numbered prefix
        label_num_match = re.match(r'^(\d+)\.\s*(.*)', label_text)
        if label_num_match:
            label_text = label_num_match.group(2).strip()
        # Try to extract content after the label
        for lbl in list(SECTION_LABELS.keys()) + [v.lower() for v in NUMERIC_FIELD_MAP.values()]:
            inline_match = re.match(r'(?i)' + re.escape(lbl) + r'[\s.:]*(.+)', label_text)
            if inline_match:
                inline_content = inline_match.group(1).strip()
                if inline_content and len(inline_content) > 3:
                    content_parts.append(inline_content)
                break

        for j in range(start_idx + 1, end_idx):  # Remaining items after the label
            text = text_items[j]
            if text and len(text) > 1:  # Skip empty and single-char items
                # Skip if it's another section label
                text_stripped = strip_bullets(text)
                stripped_num = re.match(r'^(\d+)\.\s*(.*)', text_stripped)
                if stripped_num:
                    text_stripped = stripped_num.group(2).strip()
                text_lower = text_stripped.lower().rstrip(':').rstrip('.')
                is_label = any(
                    text_lower == lbl or text_lower.startswith(lbl + ':') or text_lower.startswith(lbl + '.')
                    for lbl in SECTION_LABELS.keys()
                )
                if not is_label:
                    content_parts.append(text)

        if content_parts:
            sections[field_num] = ' '.join(content_parts)

    # Extract staff considerations — gather multiple lines after "special handling"
    for i, text in enumerate(text_items):
        if 'special handling' in text.lower():
            staff_parts = []
            for j in range(i + 1, min(i + 5, len(text_items))):
                if text_items[j]:
                    staff_parts.append(text_items[j])
            if staff_parts:
                staff_considerations = ' '.join(staff_parts)
            break

    # Validation
    if not date:
        print(f"Could not find date in {file_path}")
        return None

    requestor_id = email or requestor
    if not requestor_id:
        print(f"Could not find requestor in {file_path}")
        return None

    # Apply boilerplate stripping to sections
    for field_num in sections:
        sections[field_num] = strip_boilerplate(sections[field_num])

    # Build PromForm
    prom_form = PromForm(
        date=date,
        filename=file_path,
        requestor=requestor_id,
        request_title=title,
        chemicals_and_processes=sections.get(1),
        request_reason=sections.get(3),
        process_flow=sections.get(4),
        amount_and_form=sections.get(5),
        staff_considerations=staff_considerations,
        raw_prom="\n".join(raw_text_parts),
    )

    return prom_form


# async def embed_concat_json(concat_thread: str) -> List[float]:
#     """
#     Async version of embedding, comes post LLM JSON retrieval in the pipeline
#     """

#     response = await client.embeddings.create(
#         model = "text-embedding-ada-002",
#         input=concat_thread
#     )

#     return response.data[0].embedding

# def process_file(file_path) -> PromForm and str:
#     is_docx = file_path.lower().endswith('.docx')
#     if is_docx:
#         prom = extract_prom_from_docx(file_path, debug=False
#     else:
#         print("PDF are hanging, skipping for now")
#         # prom = extract_prom_from_docling(file_path, debug=False)
#         prom = None

#     # prom = extract_prom_unified(file_path, debug=False)
#     if prom is None:
#         return None, file_path
#     return prom, None


# def filter_duplicates(prom_forms: List[PromForm]) -> List[PromForm]:
#     """
#     Filter out duplicate PromForms based on (date, requestor, request_title).
#     Returns list of unique PromForms.
#     """
#     seen = set()
#     unique = []
#     duplicates = 0
    
#     for prom in prom_forms:
#         if prom.date is None or prom.requestor is None or prom.request_title is None:
#             continue
        
#         # Create tuple key for duplicate checking
#         key = (prom.date.lower(), prom.requestor.lower(), prom.request_title.lower())
        
#         if key in seen:
#             print(f"Duplicate found: {prom.request_title} by {prom.requestor} on {prom.date}")
#             duplicates += 1
#         else:
#             seen.add(key)
#             unique.append(prom)
    
#     if duplicates > 0:
#         print(f"Filtered out {duplicates} duplicate(s), {len(unique)} unique remaining")
    
#     return unique

# async def embed_pipeline(prom_form: PromForm, embed_sem: asyncio.Semaphore) -> PromForm:
#     # Validate only the fields that must exist to embed + insert a useful record.
#     # (Optional fields like staff_considerations should not fail the pipeline.)
#     required_fields = {
#         'date',
#         'filename',
#         'requestor',
#         'request_title',
#         'chemicals_and_processes',
#         'request_reason',
#         'process_flow',
#         'amount_and_form',
#     }
#     has_empty = [f for f in prom_form.is_empty() if f in required_fields]
#     if has_empty:
#         return f"{', '.join(has_empty)} is returning None | {prom_form.filename}"
    
#     # Build the embed string from form fields
#     embed_string = build_embed_string(prom_form)
#     if not embed_string:
#         return "Could not build embed string - missing required fields"
    
#     async with embed_sem:
#         prom_embed = await embed_concat_json(embed_string)
#     async with embed_sem:
#         process_embed = await embed_concat_json(prom_form.process_flow)
    
#     return replace(prom_form, embedded_string=embed_string, request_embedding=prom_embed, process_embedding=process_embed)

# async def run_prom_pipeline(prom_objects: List[PromForm], con):
#     embed_sem = asyncio.Semaphore(MAX_CONCURRENT_PROM_REQUESTS)
#     tasks = [embed_pipeline(prom_object, embed_sem=embed_sem) for prom_object in prom_objects]
#     for coro in asyncio.as_completed(tasks):
#         finished_prom_object = await coro
#         # Skip if embed_pipeline returned an error string
#         if isinstance(finished_prom_object, str):
#             print(finished_prom_object)
#             print(f"Skipping: {finished_prom_object}")
#             continue
#         finished_prom_object.insert_prom(con)
#         print(f"Finished Inserting {finished_prom_object.request_title}")



# if __name__ == "__main__":
#     print("--- Extracting PROM Forms ---")
#     pdf_path = "../files/promForms/"

#     cpu_count = os.cpu_count()
#     print(f"Running {cpu_count - 2} processes simultaneously")

#     con = get_db_connection()
#     try: 
#         con = init_prom_table(con, True)
#     except Exception as e:
#         print("Could not initiate Table")
#         print(e)

#     prom_dir = "../files/promForms/2019"
#     pdf_files = [os.path.join(prom_dir, f) for f in os.listdir(prom_dir) 
#                  if f.endswith(('.pdf', '.docx', '.PDF', '.DOCX'))]
#     print(f"Found {len(pdf_files)} files to process")
#     if not pdf_files:
#         print(f"No files found in {prom_dir}")
#         raise SystemExit(0)
#     t0 = time.perf_counter()
#     processed_files = 0
#     pool = Pool(processes = (cpu_count - 2))
#     results = []
#     problematic_files = []
#     try:
#         for result, bad in pool.imap_unordered(process_file, pdf_files):
#             if bad:
#                 problematic_files.append(bad)
#             elif result:
#                 processed_files += 1
#                 print(f"Finished processing {result.filename}")
#                 print(f"Finished {processed_files/len(pdf_files)*100:.1f}%")
#             results.append(result)
#     finally:
#         pool.terminate()
#         pool.join()
    
#     # Filter out None results and duplicates
#     print(f"Problematic files: {problematic_files}")
#     results = [r for r in results if r is not None]
#     results = filter_duplicates(results)
        
#     if results:
#         asyncio.run(run_prom_pipeline(results, con))
#         print(f"Pipeline complete. Processed {len(results)} unique forms.")
#     else:
#         print("No valid results to process")
    
    
    
    
    


            
    
    
    # t1 = time.perf_counter()
    # print(f"Multiprocessing Time taken: {t1 - t0} seconds")

    # t0 = time.perf_counter()

    # t2 = time.perf_counter()
    # for pdf_file in pdf_files:   
    #     try:
    #         # Use appropriate pipeline based on file type
    #         is_docx = pdf_file.lower().endswith('.docx')
    #         if is_docx:
    #             prom = extract_prom_from_docx(pdf_file, debug=False)
    #         else:
    #             prom = extract_prom_from_docling(pdf_file, debug=False)
            # if prom:
            #     print(f"Date: {prom.date}")
            #     print(f"Requestor: {prom.requestor}")
            #     print(f"Title: {prom.request_title}")
            #     print(f"\n1. Chemical/Material:\n{prom.chemicals_and_processes}")
            #     print(f"\n3. Reason:\n   {prom.request_reason}")
            #     print(f"\n4. Process Flow:\n   {prom.process_flow}")
            #     print(f"\n5. Amount/Form:\n   {prom.amount_and_form}")
            #     print(f"\nStaff Considerations:\n   {prom.staff_considerations}")
            #     # print(f"\nEmbed String:\n{build_embed_string(prom)}")
            # else:
            #     print("Failed to extract")
    #     except Exception as e:
    #         print(f"Error: {e}")
    # t3 = time.perf_counter()
    # print(f"Single Processing Time taken: {t3 - t2} seconds")
