from sqlalchemy import create_engine, text
import os
import mysql.connector
from urllib.parse import urlparse
import json



def get_super_db_connection(PROPERTY_DATABASE, clientId, connection_string):

    # Parse the connection string
    url = urlparse(connection_string)

    connection = mysql.connector.connect(
        host=url.hostname,
        user=url.username,
        password=url.password,
        database=url.path[1:],  # Removing the leading '/'
    )

    if connection.is_connected():
        if PROPERTY_DATABASE == "" or PROPERTY_DATABASE is None:
            query = f"""SELECT configuration_db FROM mst_client_db_details WHERE clientid = {clientId};"""
            cursor = connection.cursor(dictionary=True)
            try:
                cursor.execute(query)
                result = cursor.fetchall()
                return result[0] if result else None
            except Exception as e:
                print("Error:", e)
                return None
            finally:
                cursor.close()  
                connection.close()  

        else:
            query = f"""SELECT revenuconfigurationbyproperty_db 
            FROM mst_client_db_details 
            WHERE clientid = (SELECT clientid FROM pro_property WHERE propertycode = '{PROPERTY_DATABASE}' LIMIT 1);"""
            
            cursor = connection.cursor(dictionary=True) 
            try:
                cursor.execute(query)
                result = cursor.fetchall()
                return result[0] if result else None
            except Exception as e:
                print("Error:", e)
                return None
            finally:
                cursor.close()  
                connection.close() 
    else:
        print("Err:: Client Database Not connected!!!")

def get_db_connection(PROPERTY_DATABASE='', clientId='', connection_string=''):
    conn_str = get_super_db_connection(PROPERTY_DATABASE, clientId, connection_string)
    # print("Connection String:", str(conn_str))

    if PROPERTY_DATABASE == "" or PROPERTY_DATABASE is None:
        ConfigurationDb = conn_str['configuration_db']
        ConfigurationDbComponents = dict(item.strip().split('=') for item in ConfigurationDb.split(';'))  # ✅ FIXED HERE

        # print("Configuration DB Components:", ConfigurationDbComponents)

        host = ConfigurationDbComponents.get('server')
        port = ConfigurationDbComponents.get('port')
        port = int(port)  # Ensure it's an integer
        username = ConfigurationDbComponents.get('uid')
        password = ConfigurationDbComponents.get('password')
        db_name = ConfigurationDbComponents.get('database')

        conn_str = (
            f"mysql+pymysql://{username}:{password}@{host}:{port}/{db_name}"
            "?connect_timeout=30"
        )
    else:
        revenueConfigurationByPropertyDb = conn_str['revenuconfigurationbyproperty_db']
        revenueConfigurationByPropertyDbComponents = dict(
            item.strip().split('=') for item in revenueConfigurationByPropertyDb.split(';'))  # ✅ FIXED HERE

        # print("Revenue Configuration By Property DB Components:", revenueConfigurationByPropertyDbComponents)

        host = revenueConfigurationByPropertyDbComponents.get('Server')
        port = revenueConfigurationByPropertyDbComponents.get('Port')
        port = int(port)  # Ensure it's an integer
        username = revenueConfigurationByPropertyDbComponents.get('User Id')
        password = revenueConfigurationByPropertyDbComponents.get('Password')
        db_name = PROPERTY_DATABASE.replace("'", "")

        conn_str = (
            f"postgresql+psycopg2://{username}:{password}@{host}:{port}/{db_name}"
            "?connect_timeout=0"
        )
    
    # print("Final Connection String:", conn_str)

    engine = create_engine(conn_str)
    conn = engine.connect()
    return conn

