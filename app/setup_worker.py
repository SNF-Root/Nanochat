from preprocessing.database.pg import get_db_connection, init_prom_table, init_email_table

if __name__ == "__main__":
    con = None
    try:
        con = get_db_connection()
        con = init_prom_table(con=con, drop_table=False)
        con = init_email_table(con=con, drop_table=False)
        print("initialized prom_embeddings and email_embeddings tables")
    except Exception as e:
        print("worker setup failed (db connect or table init)")
        print(e)
    finally:
        if con is not None:
            con.close()
