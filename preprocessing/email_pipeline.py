import psycopg2
import time
from preprocessing.order_emails import create_dict_of_threads, get_email_by_msgid
from preprocessing.database.pg import get_db_connection, init_email_table
from preprocessing.filter_emails import extract_main_message
from preprocessing.embed_emails import run_pipeline
import asyncio
from preprocessing.models.insert import Email
import os



BANNER = r"""
/******************************************************************************\
*                                                                              *
*                         N E X T   E M A I L   T H R E A D                    *
*                                                                              *
\******************************************************************************/
"""


#entry point for proocessing emails and inserting them into the database
#preprocessing email functions in embed_emails.py


if __name__ == "__main__":

    emails_dir = "../files/emails/2019_emails"
    emails_files = [os.path.join(emails_dir, f) for f in os.listdir(emails_dir) if f.endswith(".txt")]
    print(f"Found {len(emails_files)} emails files")
    print(emails_files)


    con = get_db_connection()
    init_email_table(con=con, drop_table=True)
    for file in emails_files:
        dict_of_threads, msg_start, msg_end = create_dict_of_threads(file)
        if not dict_of_threads:
            print(f"No threads found in {file}")
            continue
        email_objects = []
        for keys, vals in dict_of_threads.items():
            date, requestor = keys
            for val in vals:
                thread = ""
                for item in val:
                    email = get_email_by_msgid(file, msg_start, msg_end, item)
                    processed_email = extract_main_message(email)
                    thread = thread + "\n" + processed_email
                email_object = Email(date=date, filepath=file, requestor=requestor, raw_thread=thread)
                email_objects.append(email_object)
        print(f"created {len(email_objects)} email objects")
        results = asyncio.run(run_pipeline(email_objects, con))
        print("finished populating db")


#TODO: ADD RATE LIMITING
