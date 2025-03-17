import os
import sys

from sqlalchemy import text
from dotenv.main import load_dotenv
load_dotenv()
sys.path.append(os.environ['PROJECT_PATH'])

from utils.db import db_config

def prepared_property_data():
    conn = db_config.get_db_connection()
    result = conn.execute(
        f"""SELECT * FROM rev_rmsproperty""")
    conn.close()
    result = result.fetchall()
    return result


if __name__ == '__main__':

    result = prepared_property_data()

    if result is None or type(result) is not list or len(result) == 0:
        print("property not available for this PMS")
    else:
        print("Total Properties :: ", len(result))

        for item in result:
            PROPERTY_ID = str(item['propertyid'])
            PROPERTY_CODE = item['propertyCode']
            query_list = [
                'REINDEX TABLE dailydata_transaction;',
                'REINDEX TABLE copy_mst_reservation;',
                'REINDEX TABLE mst_reservation;'
            ]

            conn = None
            try:
                for single_query in query_list:
                    print(f"{PROPERTY_CODE} Database Connection start!!!")
                    conn = db_config.get_db_connection(PROPERTY_DATABASE=PROPERTY_CODE)
                    if conn is None:
                        print(f"{PROPERTY_CODE} connection failed!!!")
                        continue
                    print(f"{PROPERTY_CODE} query :: {single_query}")
                    print(f"{PROPERTY_CODE} single query processing in database")
                    conn.execute(text(single_query))
                    print(f"{PROPERTY_CODE} single query processed in database")
                conn.close()
                print(f"{PROPERTY_CODE} all query processed in database")
            except Exception as e:
                print(f"{PROPERTY_CODE} Error:: {str(e)}")
            finally:
                if conn:
                    conn.close()
                    print('Database Connection close!!!')
