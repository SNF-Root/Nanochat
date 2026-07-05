import os
import shutil


UPLOAD_DIR = None


def clear_uploaded_files_dir() -> None:
    try:
        if os.path.isdir(UPLOAD_DIR):
            shutil.rmtree(UPLOAD_DIR, ignore_errors=True)
    except Exception as e:
        return f"Could not clear uploaded files {e}"


def _upload_status_key(user_id: str) -> str:
    return f"user:upload_file_status:{user_id}"
