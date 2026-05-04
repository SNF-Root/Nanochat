from pathlib import Path
from preprocessing.order_emails import create_dict_of_threads, get_email_by_msgid, BANNER
from preprocessing.filter_emails import extract_main_message

base_dir = Path("/Users/abdulhannanmohammed/Projects/PROM/files/emails/2019_emails")
out_path = Path("/Users/abdulhannanmohammed/Projects/PROM/2019_emails_reconstruct.txt")

files = sorted([p for p in base_dir.iterdir() if p.is_file()])

with out_path.open("w", encoding="utf-8", errors="replace") as out:
    out.write(f"Reconstructed threads from: {base_dir}\n")
    out.write(f"Total files: {len(files)}\n\n")

    for file_path in files:
        out.write("=" * 120 + "\n")
        out.write(f"FILE: {file_path.name}\n")
        out.write("=" * 120 + "\n\n")

        dict_of_threads, msg_start, msg_end = create_dict_of_threads(str(file_path))
        out.write(f"Threads found: {len(dict_of_threads)}\n\n")

        for identifier, thread_groups in dict_of_threads.items():
            out.write(BANNER + "\n")
            out.write(f"IDENTIFIER: {identifier}\n")

            for i, thread_ids in enumerate(thread_groups, start=1):
                out.write(f"THREAD_GROUP #{i} (messages: {len(thread_ids)})\n")
                out.write(f"MESSAGE_IDS: {thread_ids}\n\n")

                for msgid in thread_ids:
                    email_text = get_email_by_msgid(str(file_path), msg_start, msg_end, msgid)
                    cleaned_text = extract_main_message(email_text) if email_text else None
                    out.write("-" * 80 + "\n")
                    out.write(f"MSGID: <{msgid}>\n")
                    out.write("-" * 80 + "\n")
                    if cleaned_text:
                        out.write(cleaned_text)
                        if not cleaned_text.endswith("\n"):
                            out.write("\n")
                    else:
                        out.write("[Missing or fully filtered message text]\n")
                    out.write("\n")

                out.write("\n")

print(f"Wrote reconstructed threads to {out_path}")
