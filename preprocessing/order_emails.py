from concurrent.futures import thread
import re
import time
from typing import Dict, List, Tuple, Optional
from datetime import datetime
from collections import defaultdict

MBOX_FROM_RE = re.compile(r"^From\s")  
MSGID_RE = re.compile(r"^Message-ID:\s*<([^>]+)>", re.IGNORECASE)


ANGLE_RE = re.compile(r"<([^>]+)>")

BANNER = r"""
/******************************************************************************\
*                                                                              *
*                         N E X T   E M A I L   T H R E A D                    *
*                                                                              *
\******************************************************************************/
"""


def parse_mbox_threads(file_name: str) -> Tuple[Dict[str, List[str]], Dict[str, int], Dict[str, int], List[str]]:

    msg_refs: Dict[str, List[str]] = {}
    msg_start: Dict[str, int] = {}
    msg_end: Dict[str, int] = {}
    msg_order: List[str] = []


    current_start: Optional[int] = None
    current_msgid: Optional[str] = None
    current_refs: List[str] = []

    def close_current(end_pos: int):
        nonlocal current_start, current_msgid, current_refs
        if current_msgid is not None and current_start is not None:
            msg_end[current_msgid] = end_pos


    with open(file_name, "r", errors="replace") as f:
        while True:
            line_start = f.tell()
            line = f.readline()
            if not line:
                end_pos = f.tell()
                close_current(end_pos)
                break


            if MBOX_FROM_RE.match(line) and not line.startswith("From:"):
                if current_start is not None:
                    close_current(line_start)


                current_start = line_start
                current_msgid = None
                current_refs = []
                continue 


            if current_start is None:
                current_start = 0

            if "References:" in line:
                current_refs.extend(ANGLE_RE.findall(line))
                continue

            if line.startswith("<") and "https" not in line:
                current_refs.extend(ANGLE_RE.findall(line))
                continue


            m = MSGID_RE.match(line)
            if m:
                current_msgid = m.group(1)
                msg_refs[current_msgid] = current_refs.copy()
                msg_start[current_msgid] = current_start
                msg_order.append(current_msgid)


                continue


    return msg_refs, msg_start, msg_end, msg_order


def parent_emails(msg_refs: Dict[str, List[str]]) -> List[str]:
    return [msg for msg, refs in msg_refs.items() if len(refs) == 0]


def join_emails_by_root(msg_refs: Dict[str, List[str]], root_msgid: str) -> List[str]:

    thread = [root_msgid]
    for msg, refs in msg_refs.items():
        if msg != root_msgid and root_msgid in refs:
            thread.append(msg)
    return thread


def create_dict_of_threads(file_name: str):
    dict_of_threads = defaultdict(list)
    start = time.perf_counter()
    msg_refs, msg_start, msg_end, msg_order = parse_mbox_threads(file_name)
    end = time.perf_counter()
   

    start = time.perf_counter()
    roots = parent_emails(msg_refs)
    end = time.perf_counter()
    

    order_pos = {mid: i for i, mid in enumerate(msg_order)}

    start = time.perf_counter()
    with open(file_name, "r", errors="replace") as f:
        for root in roots:

            thread_ids = join_emails_by_root(msg_refs, root)

            thread_ids.sort(key=lambda mid: order_pos.get(mid, 10**18))
            if thread_ids:
                first_msg_id = thread_ids[0]
                first_start = msg_start[first_msg_id]

                f.seek(first_start)
                first_line = f.readline().strip()
                id_list = format_identifier_line(first_line)
                
                dict_of_threads[id_list].append(thread_ids.copy())
            else:
                print("thread_ids empty")

    end = time.perf_counter()
    print(f"main loop took {end - start} seconds")
    return dict_of_threads, msg_start, msg_end




def format_identifier_line(line: str) -> Tuple[str, str]:
    m = re.search(
        r"From (\S+)\s+at\s+(\S+)\s+\w+\s+([A-Z][a-z]{2})\s+(\d{1,2})\s+[\d:]+\s+(\d{4})",
        line
    )
    if not m:

        return ("", "")

    tag = m.group(1) + "@" + m.group(2)


    month_str = m.group(3)
    day = int(m.group(4))
    year = int(m.group(5))

    month_num = datetime.strptime(month_str, "%b").month

    date_str = f"{month_num:02d}/{day:02d}/{year}"

    return (date_str, tag)


def get_email_by_msgid(file_name: str, msg_start: Dict[str, int], msg_end: Dict[str, int], msgid: str,) -> Optional[str]:
    msgid = msgid.strip()
    if msgid.startswith("<") and msgid.endswith(">"):
        msgid = msgid[1:-1]

    s = msg_start.get(msgid)
    if s is None:
        return None

    e = msg_end.get(msgid)
    with open(file_name, "r", errors="replace") as f:
        if e is None:
            f.seek(0, 2) 
            e = f.tell()

        f.seek(s)
        return f.read(e - s)

if __name__ == "__main__":
    files = ["emails2.txt"]
    base_dir = "emails/"

    for fname in files:
        path = base_dir + fname
        dict_of_threads, msg_start, msg_end = create_dict_of_threads(path)

        elements = dict_of_threads.get(('06/19/2023', 'narunl@stanford.edu'))
        print(elements)

        for k, v in dict_of_threads.items():
            if len(v) > 1:
                print(k, v)

        print(BANNER)

        print(msg_start)
        
        print(BANNER)

        print(msg_end)

    
