import csv
import sqlite3
from datetime import datetime, timezone


def parse_date(date_string):
    try:
        return datetime.strptime(date_string, "%Y-%m-%d %H:%M:%S%z").replace(tzinfo=timezone.utc)
    except ValueError:
        return datetime.strptime(date_string, "%Y-%m-%dT%H:%M:%S.%f").replace(tzinfo=timezone.utc)


def tsv_to_sqlite(tsv_file, db_file, table_name):
    conn = sqlite3.connect(db_file)
    cursor = conn.cursor()

    try:
        with open(tsv_file, "r", newline="", encoding="utf-8") as tsvfile:
            tsvreader = csv.reader(tsvfile, delimiter="\t")
            headers = next(tsvreader)  # Get column names from the first row

            # Create table with appropriate data types
            create_table_query = f"""
            CREATE TABLE IF NOT EXISTS {table_name} (
                ID TEXT PRIMARY KEY,
                Published DATETIME,
                Added DATETIME,
                Title TEXT
            )
            """
            cursor.execute(create_table_query)

            # Insert data
            insert_query = f"INSERT OR REPLACE INTO {table_name} (ID, Published, Added, Title) VALUES (?, ?, ?, ?)"

            for row in tsvreader:
                if len(row) != 4:
                    print(f"Warning: Row {tsvreader.line_num} has {len(row)} fields, expected 4. Skipping this row.")
                    continue
                try:
                    # Parse dates
                    published_date = parse_date(row[1])
                    added_date = parse_date(row[2])

                    # Insert data
                    cursor.execute(insert_query, (row[0], published_date, added_date, row[3]))
                except sqlite3.Error as e:
                    print(f"Error inserting row {tsvreader.line_num}: {e}")
                    print(f"Problematic row: {row}")
                except ValueError as e:
                    print(f"Error parsing date in row {tsvreader.line_num}: {e}")
                    print(f"Problematic row: {row}")

        conn.commit()
        print(f"Data from {tsv_file} has been successfully imported into {db_file}")

    except Exception as e:
        print(f"An error occurred: {e}")

    finally:
        conn.close()


# Example usage
tsv_to_sqlite("/Users/anilkeshwani/Desktop/journal/PDFs/index.tsv", "papers.db", "arxiv_papers")
