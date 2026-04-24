import pypdfium2 as pdfium
from pathlib import Path
import re
import pypdfium2.internal as pdfium_i
import docx2txt
from preprocessing.models.insert import PromForm
from preprocessing.rgx_pattern import collapse_spaces, extract_date_from_section, first_span_after, fuzzy_find_header, strip_boilerplate


#OLD CODE; ALL NECESSARY FUNCTIONS ARE BEING IMPORTED INTO prom_pipeline.py
#MOVE TO prom_pipeline.py FOR ENTRY



target_list = [
    "Title",
    "Requestor:",
    "Date:",
    "1. The chemical or material",
    "2. Vendor/manufacturer info",
    "3. Reason for request",
    "4. Process Flow",
    "5. Amount and form",
    "6. Storage",
    "7. Disposal",
]



def fork_then_extract(file_path) -> PromForm:
    is_docx = file_path.lower().endswith('.docx')
    is_pdf = file_path.lower().endswith(".pdf")
    if is_docx:
        cleaned_string = docx_string_maker(file_path)
    elif is_pdf:
        cleaned_string = pdf_string_maker(file_path)
    else:
        return "Invalid file format passed"
    promform = extract_to_promform(cleaned_string, file_path)
    return promform

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


def pdf_string_maker(file_path: str) -> str:
    pdf = pdfium.PdfDocument(file_path)
    cleaned_text = ""

    for i in range(len(pdf)):
        page = pdf[i]
        textpage = page.get_textpage()
        text_all = textpage.get_text_bounded()
        page_text = collapse_spaces(text_all)
        cleaned_text += page_text + " "
        textpage.close()
        page.close()
    pdf.close()
    

    return cleaned_text

def docx_string_maker(file_path: str) -> str:
    docx_text = docx2txt.process(file_path)
    cleaned_text = collapse_spaces(docx_text)
    return cleaned_text


def extract_to_promform(cleaned_text: str, file_path: str ) -> PromForm:

    """
    args:
    cleaned_text is a string that has the whole file in it, its been cleaned to remove whitespace, and extra spaces.
    file_path is simply used as an identifier to show which file errored
    """


    numbered_fields = {}
    min_header_start = 0

    for t_idx in range(len(target_list)):
        current_header_candidates = fuzzy_find_header(cleaned_text, target_list[t_idx])
        current_header_span = first_span_after(current_header_candidates, min_header_start)
        if current_header_span is None:
            print(f"Can't find target: {target_list[t_idx]} in {file_path}")
            numbered_fields[t_idx] = ""
            return f"Can't find target: {target_list[t_idx]} in {file_path}"
        start_pos = current_header_span[1]
        min_header_start = start_pos


        if t_idx < (len(target_list) - 1):
            next_header_candidates = fuzzy_find_header(cleaned_text, target_list[t_idx + 1])
            next_header_span = first_span_after(next_header_candidates, start_pos)
            if next_header_span is None:
                end_pos = len(cleaned_text)
            else:
                end_pos = next_header_span[0]
        else:
            end_pos = len(cleaned_text)
        section_text = cleaned_text[start_pos:end_pos]
        section_text = re.sub(r"^[\s:.\-]+", "", section_text).strip()
        numbered_fields[t_idx] = section_text


    date_section = numbered_fields.get(2, "")
    extracted_date = extract_date_from_section(date_section)

    prom_form = PromForm(
        date = extracted_date,
        filename = Path(file_path).name,
        requestor = strip_boilerplate(numbered_fields.get(1, "")),
        request_title = strip_boilerplate(numbered_fields.get(0, "")),
        chemicals_and_processes = strip_boilerplate(numbered_fields.get(3, "")),
        request_reason = strip_boilerplate(numbered_fields.get(5, "")),
        process_flow = strip_boilerplate(numbered_fields.get(6, "")),
        amount_and_form = strip_boilerplate(numbered_fields.get(7, ""))
    )

    return prom_form


def print_problematic_file_texts(trouble_files):
    if not trouble_files:
        print("\nNo problematic files to inspect.")
        return

    for idx, trouble_item in enumerate(trouble_files, start=1):
        file_path, missing_target = trouble_item
        file_path = Path(file_path)
        suffix = file_path.suffix.lower()

        if suffix == ".docx":
            extracted_text = docx_string_maker(file_path)
        elif suffix == ".pdf":
            extracted_text = pdf_string_maker(str(file_path))
        else:
            extracted_text = f"UNSUPPORTED FILE FORMAT: {suffix}"

        print("\n" + "=" * 100)
        print(f"PROBLEM FILE {idx}/{len(trouble_files)}")
        print(f"File: {file_path.name}")
        print(f"Type: {suffix or 'NO_SUFFIX'}")
        print(f"Missing target: {missing_target}")
        print("-" * 100)
        print("EXTRACTED TEXT")
        print("-" * 100)
        print(extracted_text)
        print("=" * 100)





if __name__ == "__main__":
    directory = Path(__file__).parent.parent / "files" / "promForms" / "2020"
    pdfs = [file for file in directory.iterdir()]
    print(f"Found {len(pdfs)} PDF files")
    trouble_files = []
    counter = 0
    for pdf_file in pdfs:
        if pdf_file.suffix == ".docx":
            cleaned_text = docx_string_maker(pdf_file)
        elif pdf_file.suffix == ".pdf":
            cleaned_text = pdf_string_maker(pdf_file)
        else:
            print("UNSUPPORTED FILE FORMAT")
        print(f"\nProcessing: {pdf_file.name}")
        result = extract_to_promform(cleaned_text, str(pdf_file))
        if isinstance(result, str):
            trouble_files.append([pdf_file, result])
            continue
        print("\nReturned PromForm data:")
        for key, value in result.items():
            preview = (
                value[:50] + "..."
                if isinstance(value, str) and len(value) > 50
                else value
            )
            print(f"  {key}: {preview}")
            # counter+=1

        print("\n" + "=" * 70)
        counter+=1
    print(f"completed {(counter/len(pdfs)) * 100}% or {counter}/{len(pdfs)}")
    print("Trouble Files")
    print(trouble_files)
    print_problematic_file_texts(trouble_files)
