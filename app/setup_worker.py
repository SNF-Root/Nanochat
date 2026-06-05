from preprocessing.database.pg import (
    get_db_connection,
    init_prom_table,
    init_email_table,
    init_all_table,
)

if __name__ == "__main__":
    con = None
    drop_table: bool = True
    user_choice = ""
    if drop_table:
        print("DROP TABLE ON")
        user_choice = input("do you want to drop all tables? y or n")
    if user_choice == "n":
        drop_table=False
    try:
        con = get_db_connection()
        con = init_prom_table(con=con, drop_table=drop_table)
        con = init_email_table(con=con, drop_table=drop_table)
        con = init_all_table(con=con, drop_table=drop_table)
        print("initialized prom_embeddings, email_embeddings, and all_embeddings tables")
    except Exception as e:
        print("worker setup failed (db connect or table init)")
        print(e)
    finally:
        if con is not None:
            con.close()
