from preprocessing.database.pg import get_db_connection, init_prom_table, init_email_table

if __name__ == "__main__":
    try:
        con = get_db_connection()
        try:
            con = init_prom_table(con=con, drop_table=False)
            con = init_email_table(con=con, drop_table=False )
        except Exception as e:
            print("could not init prom table")
            print(e)
    except Exception as e:
        print("could not connect to db")
        print(e)
