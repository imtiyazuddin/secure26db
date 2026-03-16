import subprocess
import time
import psycopg2
from contextlib import contextmanager


# ---- Configuration ----
DB_CONFIG = {
    "dbname": "postgres",
    "user": "postgres",
    "password": "secure26DBPostgreSQL",
    "host": "localhost",
    "port": 5432,
}

SUDO_PASSWORD = "#secure26DB\n" # give your linux sudo user password, ending with \n


# ---- Database Helper ----
@contextmanager
def get_connection():
    conn = psycopg2.connect(**DB_CONFIG)
    try:
        yield conn
    finally:
        conn.close()


def run_query(query):
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query)
            return cur.fetchone()


# ---- Logic Blocks ----
def dummy_logic(label):
    print(f"Running {label}...")
    result = run_query("SELECT now();")
    print(f"{label} time:", result)


# ---- Restart Logic ----
def restart_postgres():
    print("Restarting PostgreSQL...")
    subprocess.run(
        ["sudo", "-S", "systemctl", "restart", "postgresql"],
        input=SUDO_PASSWORD.encode(),
        check=True
    )
    print("Restart command issued.")


def wait_until_ready(timeout=30):
    print("Waiting for PostgreSQL to become ready...")
    start = time.time()

    while True:
        try:
            with get_connection():
                print("PostgreSQL is ready.")
                return
        except psycopg2.OperationalError:
            if time.time() - start > timeout:
                raise TimeoutError("PostgreSQL did not start in time.")
            time.sleep(1)


# ---- Main Execution ----
if __name__ == "__main__":
    dummy_logic("Dummy logic 1")
    restart_postgres()
    wait_until_ready()
    dummy_logic("Dummy logic 2")
