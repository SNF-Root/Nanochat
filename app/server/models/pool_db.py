from psycopg2.pool import ThreadedConnectionPool

__pool = None


def init_pool(minconn=5, maxconn=10, dsn = None):
    if dsn is None:
        print("No DSN set")
        return None
    global __pool
    if __pool is not None:
        return __pool
    __pool = ThreadedConnectionPool(minconn=minconn, maxconn=maxconn, dsn=dsn)
    return __pool



def get_db_connection():
    return __pool.getconn()

def release_db_conn(con):
    return __pool.putconn(con)

def close_all_conns():
    return __pool.closeall()