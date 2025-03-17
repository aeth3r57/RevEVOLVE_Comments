import sys

from sqlalchemy import text

sys.path.append("..")
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

        # query_list = ["""HELLO"""]
        query_list = []

        for single_query in query_list:



            for item in result:
                PROPERTY_ID = str(item['propertyid'])
                PROPERTY_CODE = item['propertyCode']

                conn = None
                try:
                    # single_query = """ALTER TABLE public.rev_rateplan ALTER COLUMN rateplanid DROP DEFAULT;"""

                    print(f"{PROPERTY_CODE} Start!!!")
                    conn = db_config.get_db_connection(PROPERTY_DATABASE=PROPERTY_CODE)
                    if conn is None:
                        print(f"{PROPERTY_CODE} connection failed!!!")
                        continue
                    print(f"{PROPERTY_CODE} query :: {single_query}")
                    print(f"{PROPERTY_CODE} query processing in database")
                    conn.execute(text(single_query))
                    conn.close()
                    print(f"{PROPERTY_CODE} query processed in database")
                except Exception as e:
                    print(f"{PROPERTY_CODE} Error:: {str(e)}")
                finally:
                    if conn:
                        conn.close()
                        print('Connection close!!!')

