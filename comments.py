import json
import openai
from datetime import datetime, date, timedelta
import time
from decimal import Decimal 
from prompt_templates import PROMPT_TEMPLATES
import re
import os
import arrow
import calendar
import traceback
from utils.db import db_config
from sqlalchemy import text
import mysql.connector
from urllib.parse import urlparse


from dotenv import load_dotenv

load_dotenv()

# Database credentials
openai.api_key = os.getenv("OPENAI_API_KEY")

MASTER_DB_HOST = os.getenv("MASTER_DB_HOST")
MASTER_DB_PORT = os.getenv("MASTER_DB_PORT")
MASTER_DB_NAME = os.getenv("MASTER_DB_NAME")
MASTER_DB_USERNAME = os.getenv("MASTER_DB_USERNAME")
MASTER_DB_PASSWORD = os.getenv("MASTER_DB_PASSWORD")

db_connection_string = f"mysql://{MASTER_DB_USERNAME}:{MASTER_DB_PASSWORD}@{MASTER_DB_HOST}:{MASTER_DB_PORT}/{MASTER_DB_NAME}"

def get_asofdate(PROPERTY_CODE, conn):
    try:
        aod_query = text("""SELECT MAX("AsOfDate") FROM dailydata_transaction WHERE "propertyCode" = :property_code""")

        result = conn.execute(aod_query, {"property_code": PROPERTY_CODE})
        AS_OF_DATE = result.scalar()

        if AS_OF_DATE is None:
            # raise ValueError("❌ Error: No AS_OF_DATE found for the given propertyCode.")
            print ("❌ Error: No AS_OF_DATE found for the given propertyCode.")
            return None, None

        AS_OF_DATE = AS_OF_DATE.strftime("%Y-%m-%d")
        date_obj = datetime.strptime(AS_OF_DATE, '%Y-%m-%d')
        year = int(date_obj.year)

        print("AS_OF_DATE:", AS_OF_DATE)

        return AS_OF_DATE, year
    
    except Exception as e:
        err_msg = f"Error : {str(e)}"
        traceback_info = traceback.format_exc()
        print(f"{err_msg}\nTraceback:\n{traceback_info}")

def get_month_start_end_dates(as_of_date, years_offset=0):
    """Returns the first and last date of the month for a given date, 
    with an optional year offset (default: 0 for current year, -1 for previous year)."""
    
    as_of_dt = datetime.strptime(as_of_date, "%Y-%m-%d")
    year, month = as_of_dt.year + years_offset, as_of_dt.month  # Apply offset to year

    # First and last day of the month
    start_date = f"{year}-{month:02d}-01"
    end_date = f"{year}-{month:02d}-{calendar.monthrange(year, month)[1]}"
    print("Start Date:", start_date, "End Date:", end_date)
    return start_date, end_date

def get_market_seg_room_type(PROPERTY_CODE, conn):
    try:
        ms_query = text("""SELECT "MarketSegment" from copy_mst_reservation WHERE "propertyCode" = :property_code GROUP BY "MarketSegment" """)
        
        result = conn.execute(ms_query, {"property_code": PROPERTY_CODE})

        market_segments = result.fetchall()

        market_segment_list = [market_segment[0] for market_segment in market_segments]

        market_segment_string = ",".join(market_segment_list)

        # print("Market Segments:", market_segment_string)

        rt_query = text("""SELECT "roomtypecode" from rev_roomtype WHERE "propertycode" = :property_code GROUP BY "roomtypecode" """)

        result = conn.execute(rt_query, {"property_code": PROPERTY_CODE})

        room_types = result.fetchall()

        room_type_list = [room_type[0] for room_type in room_types]

        room_type_string = ",".join(room_type_list)

        # print("Room Types:", room_type_string)

        return market_segment_string, room_type_string

    except Exception as e:
        err_msg = f"Error : {str(e)}"
        traceback_info = traceback.format_exc()
        print(f"{err_msg}\nTraceback:\n{traceback_info}")

def fetch_data(conn, query, params=None):
            """Fetch data using a cursor, format results, and return them as a list of dictionaries."""
            formatted_results = []
            result = conn.execute(text(query), params or {})

            columns = result.keys()  # Get column names
            for row in result.fetchall():
                row_dict = dict(zip(columns, row))
                for key, value in row_dict.items():
                    if isinstance(value, (datetime, date)):  
                        row_dict[key] = value.strftime("%Y-%m-%d")
                    elif isinstance(value, Decimal):  
                        row_dict[key] = float(value)
                formatted_results.append(row_dict)

            return formatted_results

def generate_summary(data, prompt_type):
    try:

        json_data_string = json.dumps(data, indent=2)
        # print(json_data_string)

        if prompt_type not in PROMPT_TEMPLATES:
            return {"error": "Invalid prompt type."}

        instruction = PROMPT_TEMPLATES[prompt_type]()
        
        # TODO: Uncomment the below code to generate summary using OpenAI API
        
        response = openai.ChatCompletion.create(
            model="gpt-4o",
            messages=[{"role": "system", "content": instruction},{"role": "user", "content": f"Here is the JSON data for processing:\n{json_data_string}"}],
            temperature=0.2,
        )

        generated_summary = response["choices"][0]["message"]["content"]

        formatted_summary = re.sub(r"^```html\n", "", generated_summary)
        formatted_summary = re.sub(r"\n```$", "", formatted_summary)

        # print("Generated Summary:", formatted_summary)

        return {formatted_summary}
        
    except Exception as e:
        print(f"❌ Error: {e}")
        err_msg = f"Error fetching inventory: {str(e)}"
        traceback_info = traceback.format_exc()  # Get full traceback details
        print(f"{err_msg}\nTraceback:\n{traceback_info}")
        return (f"error: {str(e)}")

def save_comments(comments, PROPERTY_CODE, AS_OF_DATE, CLIENT_ID, db_connection_string, componentname):
    try:
        conn = db_config.get_db_connection(PROPERTY_DATABASE='', clientId=CLIENT_ID, connection_string=db_connection_string)

        # ✅ Wrap the query with `text()`
        widget_id_query = text('SELECT widgetid FROM mst_widget WHERE componentname = :componentname')
        widget_id = conn.execute(widget_id_query, {"componentname": componentname}).scalar()
        print("Widget ID:", widget_id)

        # ✅ Fetch User ID
        user_id_query = text('SELECT userid FROM usr_user WHERE issystemuser IS TRUE')
        user_id = conn.execute(user_id_query).scalar()
        print("User ID:", user_id)

        # ✅ Fetch Property ID
        property_id_query = text('SELECT propertyid FROM pro_property WHERE propertycode = :property_code ORDER BY propertyid LIMIT 1')
        property_id = conn.execute(property_id_query, {"property_code": PROPERTY_CODE}).scalar()
        print("Property ID:", property_id)

        createdon = arrow.get(AS_OF_DATE).replace(hour=23, minute=59, second=59)
        print("Created On:", createdon)

        # ✅ DELETE Existing Comments
        delete_comment_query = text("""
            DELETE FROM usr_widgetnote
            WHERE title = :title
            AND widgetid = :widget_id
            AND userid = :user_id
            AND propertyid = :property_id
            AND associationid = :widget_id
            AND associationtype = 'widget';
        """)

        conn.execute(
            delete_comment_query.bindparams(
                widget_id=widget_id,
                user_id=user_id,
                property_id=property_id,
                title=f"{componentname} By Nova"  # Dynamically set title
            )
        )

        conn.commit()

        print("Old Comments deleted successfully.")

        # ✅ INSERT New Comments
        insert_comment_query = text("""
            INSERT INTO usr_widgetnote 
            (widgetid, userid, createdon, widgetnotes, isactive, propertyid, title, asofdate, associationid, associationtype)
            VALUES 
            (:widget_id, :user_id, :createdon, :comments, :isactive, :property_id, :title, :asofdate, :widget_id, 'widget');
        """)

        conn.execute(
            insert_comment_query.bindparams(
                widget_id=widget_id,
                user_id=user_id,
                createdon=createdon,
                comments=comments,
                isactive=True,
                property_id=property_id,
                asofdate=AS_OF_DATE,
                title=f"{componentname} By Nova"
            )
        )

        conn.commit()

        print("New Comment inserted successfully.")

    except Exception as e:
        err_msg = f"Error saving comments: {str(e)}"
        traceback_info = traceback.format_exc()
        print(f"{err_msg}\nTraceback:\n{traceback_info}")
        return {"status_code": 0, "message": "Error saving comments", "error": str(e)}

    finally:
        if 'conn' in locals() and conn is not None:
            conn.close()

def check_data(response_json, componentname, AS_OF_DATE, PROPERTY_CODE, CLIENT_ID, db_connection_string):
    try:
        if not isinstance(response_json, dict):
            print("❌ Error: Data is not in dictionary format.")
            print("Cannot generate summary.")
            print("Exiting")
            return
        else:
            summary = generate_summary(response_json, componentname)
            if not isinstance(summary, set):
                print("❌ Error: Comments not generated in set format.")
                print("No data available to save in database")
                print("Exiting")
                return
            else:
                save_comments(summary, PROPERTY_CODE, AS_OF_DATE, CLIENT_ID, db_connection_string, componentname)
                print("Comments saved successfully.")
                return
            
    except Exception as e:
        err_msg = f"Error : {str(e)}"
        traceback_info = traceback.format_exc()
        print(f"{err_msg}\nTraceback:\n{traceback_info}")
    finally:
        pass

def get_AnnualSummary(PROPERTY_CODE, AS_OF_DATE, CLIENT_ID, year, conn, componentname):
    try:
        total_ly_query = """
            SELECT 
                "propertyCode",
                "AsOfDate"::text AS "AsOfDate", 
                "year",
                "month",
                "occ",
                "rms",
                "adr",
                "rev"
            FROM snp_annsmry_total_ly 
            WHERE "AsOfDate" = :as_of_date
            AND "propertyCode" = :property_code 
            AND "year" = :year;
        """

        total_ly_json = fetch_data(conn, total_ly_query, {
            "as_of_date": AS_OF_DATE,
            "property_code": PROPERTY_CODE,
            "year": year
        })

        otb_query = """
            SELECT 
                "propertyCode",
                "AsOfDate"::text AS "AsOfDate",
                "year",
                "month",
                "occ",
                "rms",
                "adr",
                "rev"
            FROM snp_annsmry_on_the_book
            WHERE "AsOfDate" = :as_of_date
            AND "propertyCode" = :property_code
            AND "year" = :year;
        """

        otb_json = fetch_data(conn, otb_query, {
            "as_of_date": AS_OF_DATE,
            "property_code": PROPERTY_CODE,
            "year": year
        })

        net_stly_query = """
            SELECT 
                "propertyCode",
                "AsOfDate"::text AS "AsOfDate",
                "year",
                "month",
                "occ",
                "rms",
                "adr",
                "rev"
            FROM snp_annsmry_net_stly
            WHERE "AsOfDate" = :as_of_date
            AND "propertyCode" = :property_code
            AND "year" = :year;
        """

        net_stly_json = fetch_data(conn, net_stly_query, {
            "as_of_date": AS_OF_DATE,
            "property_code": PROPERTY_CODE,
            "year": year
        })

        response_json = {
            "otb_current": otb_json,
            "net_stly": net_stly_json,
            "total_ly": total_ly_json
        }

        check_data(response_json, componentname, AS_OF_DATE, PROPERTY_CODE, CLIENT_ID, db_connection_string)

    except Exception as e:
        err_msg = f"Error fetching annual summary data: {str(e)}"
        traceback_info = traceback.format_exc()
        print(f"{err_msg}\nTraceback:\n{traceback_info}")
        return None, {"status_code": 0, "message": "Error fetching data", "error": str(e)}

def get_ForecastCommon(PROPERTY_CODE, AS_OF_DATE, CLIENT_ID, year, conn, componentname):
    try:
        
        otb_query = """
            SELECT 
                "propertyCode",
                "AsOfDate"::text AS "AsOfDate",
                "year",
                "month",
                "occ",
                "rms",
                "adr",
                "rev"
            FROM snp_annsmry_on_the_book
            WHERE "AsOfDate" = :as_of_date
            AND "propertyCode" = :property_code
            AND "year" = :year;
        """

        otb_json = fetch_data(conn, otb_query, {
            "as_of_date": AS_OF_DATE,
            "property_code": PROPERTY_CODE,
            "year": year
        })

        sys_forecast_query = """
            SELECT 
                "propertyCode",
                "AsOfDate"::text AS "AsOfDate",
                "year",
                "month",
                "occ",
                "rms",
                "adr",
                "rev"
            FROM snp_fc_spider
            WHERE "AsOfDate" = :as_of_date
            AND "propertyCode" = :property_code
            AND "year" = :year;
        """

        sys_forecast_json = fetch_data(conn, sys_forecast_query, {
            "as_of_date": AS_OF_DATE,
            "property_code": PROPERTY_CODE,
            "year": year
        })

        nova_forecast_query = """
            SELECT 
                "propertyCode",
                CAST(:as_of_date AS DATE) AS "AsOfDate",
                "year",
                "month",
                "occ",
                "rms",
                "adr",
                "rev"
            FROM snp_fc_nova
            WHERE "AsOfDate" = (SELECT MAX("AsOfDate") FROM snp_fc_nova)
            AND "propertyCode" = :property_code
            AND "year" = :year;
        """

        nova_forecast_json = fetch_data(conn, nova_forecast_query, {
            "as_of_date": AS_OF_DATE,
            "property_code": PROPERTY_CODE,
            "year": year
        })

        ann_budget_query = """
            SELECT 
                "propertyCode",
                CAST(:as_of_date AS DATE) AS "AsOfDate",
                "year",
                "month",
                "occ",
                "rms",
                "adr",
                "rev"
            FROM snp_annsmry_budget
            WHERE "propertyCode" = :property_code
            AND "year" = :year;
        """

        ann_budget_json = fetch_data(conn, ann_budget_query, {
            "as_of_date": AS_OF_DATE,
            "property_code": PROPERTY_CODE,
            "year": year
        })

        response_json = {
            "otb_current": otb_json,
            "system_forecast": sys_forecast_json,
            "nova_forecast": nova_forecast_json,
            "Budget": ann_budget_json
        }

        check_data(response_json, componentname, AS_OF_DATE, PROPERTY_CODE, CLIENT_ID, db_connection_string)
    
    except Exception as e:
        err_msg = f"Error : {str(e)}"
        traceback_info = traceback.format_exc()
        print(f"{err_msg}\nTraceback:\n{traceback_info}")
        return None, {"status_code": 0, "message": "Error fetching data", "error": str(e)}
    
def get_PickupCommon(PROPERTY_CODE, AS_OF_DATE, CLIENT_ID, year, conn, componentname):
    try:
        otb_query = """
            SELECT 
                "propertyCode",
                "AsOfDate"::text AS "AsOfDate",
                "year",
                "month",
                "occ",
                "rms",
                "adr",
                "rev"
            FROM snp_annsmry_on_the_book
            WHERE "AsOfDate" = :as_of_date
            AND "propertyCode" = :property_code
            AND "year" = :year;
        """

        otb_json = fetch_data(conn, otb_query, {
            "as_of_date": AS_OF_DATE,
            "property_code": PROPERTY_CODE,
            "year": year
        })

        one_day_query = """
                SELECT 
                "propertyCode",
                "AsOfDate"::text AS "AsOfDate",
                "year",
                "month",
                "occ",
                "rms",
                "adr",
                "rev"
            FROM snp_pickup_one_day
            WHERE "AsOfDate" = :as_of_date
            AND "propertyCode" = :property_code
            AND "year" = :year;
        """

        one_day_json = fetch_data(conn, one_day_query, {
            "as_of_date": AS_OF_DATE,
            "property_code": PROPERTY_CODE,
            "year": year
        })

        one_day_forecast_change_query = """
            SELECT 
                "id",
                "propertyCode",
                "AsOfDate"::text AS "AsOfDate",
                "year",
                "month",
                "occ",
                "rms",
                "adr",
                "rev"
            FROM snp_pickup_one_day_forcast_change
            WHERE "AsOfDate" = :as_of_date
            AND "propertyCode" = :property_code
            AND "year" = :year;
        """

        one_day_forecast_change_json = fetch_data(conn, one_day_forecast_change_query, {
            "as_of_date": AS_OF_DATE,
            "property_code": PROPERTY_CODE,
            "year": year
        })

        seven_day_query = """
            SELECT 
                "propertyCode",
                "AsOfDate"::text AS "AsOfDate",
                "year",
                "month",
                "occ",
                "rms",
                "adr",
                "rev"
            FROM snp_pickup_seven_day
            WHERE "AsOfDate" = :as_of_date
            AND "propertyCode" = :property_code
            AND "year" = :year;
        """

        seven_day_json = fetch_data(conn, seven_day_query, {
            "as_of_date": AS_OF_DATE,
            "property_code": PROPERTY_CODE,
            "year": year
        })

        seven_day_forecast_change_query = """
            SELECT 
                "id",
                "propertyCode",
                "AsOfDate"::text AS "AsOfDate",
                "year",
                "month",
                "occ",
                "rms",
                "adr",
                "rev"
            FROM snp_pickup_seven_day_forcast_change
            WHERE "AsOfDate" = :as_of_date
            AND "propertyCode" = :property_code
            AND "year" = :year;
        """

        seven_day_forecast_change_json = fetch_data(conn, seven_day_forecast_change_query, {
            "as_of_date": AS_OF_DATE,
            "property_code": PROPERTY_CODE,
            "year": year
        })

        response_json = {
            "otb_current": otb_json,
            "one_day_pickup": one_day_json,
            "one_day_forecast_change": one_day_forecast_change_json,
            "seven_day_pickup": seven_day_json,
            "seven_day_forecast_change": seven_day_forecast_change_json
        }

        # print("Response JSON:", response_json)

        check_data(response_json, componentname, AS_OF_DATE, PROPERTY_CODE, CLIENT_ID, db_connection_string)

        return 
    
    except Exception as e:
        err_msg = f"Error : {str(e)}"
        traceback_info = traceback.format_exc()
        print(f"{err_msg}\nTraceback:\n{traceback_info}")
        return None, {"status_code": 0, "message": "Error fetching data", "error": str(e)}

def get_ORG(PROPERTY_CODE, AS_OF_DATE, CLIENT_ID, year, conn, componentname):
    try:
        start_date, end_date = get_month_start_end_dates(AS_OF_DATE)
        
        as_of_date = datetime.strptime(AS_OF_DATE, "%Y-%m-%d").date()
        pickup_date = as_of_date - timedelta(days=1)
        seven_day_pickup_date = as_of_date - timedelta(days=7)


        transient_current_year_query = text("""
    SELECT
        "OutOfOrder" AS "OOO",
        CAST("Dates" AS TEXT) AS "Date",
        "Inventory" AS "RoomAvailable",
        CAST("AvailableOccupancy" AS INTEGER) AS "LeftToSell",
        "RoomSold" AS "OnTheBook",
        CAST("Occperc" AS INTEGER) AS "TotalOCCPercentage",
        CAST("ADR" AS INTEGER) AS "ADR",
        CAST("TotalRevenue" AS INTEGER) AS "REV",
        CAST("RevPAR" AS INTEGER) AS "RevPAR",
        "GroupOTB" AS "OTB",
        "GroupBlock" AS "Block"
    FROM
        dailydata_transaction
    WHERE
        "AsOfDate" = :as_of_date
        AND "propertyCode" = :property_code
        AND "Dates" BETWEEN
            DATE_TRUNC('month', :as_of_date)
            AND
            (DATE_TRUNC('month', :as_of_date) + INTERVAL '1 month' - INTERVAL '1 day')
""")

        transient_current_year_json = fetch_data(conn, transient_current_year_query, {
            "as_of_date": as_of_date,
            "property_code": PROPERTY_CODE
        })


        bar_based_stats_proc = text("""
            DO $$ 
            DECLARE
                code text := :property_code;
                start_date DATE := :start_date;
                end_date DATE := :end_date;
                asofdate DATE := :as_of_date;
            BEGIN
                DROP TABLE IF EXISTS temp_forcast_r28;   
                CREATE TEMP TABLE temp_forcast_r28 AS 
                SELECT
                    asofdate as "AsOfDate",
                    generate_series(
                        start_date,
                        end_date,
                        interval '1 DAY'
                    )::date AS "StayDate",
                    0 as "OTB",
                    0 as "8 Week Rolling AVG"; 

                DROP TABLE IF EXISTS temp_intermediate;
                CREATE TEMP TABLE temp_intermediate AS (
                    SELECT
                        "AsOfDate",
                        "StayDate",
                        SUM("RoomNight") AS "OTB"
                    FROM copy_mst_reservation
                    WHERE
                        "propertyCode" = code
                        AND "AsOfDate" = asofdate
                        AND "StayDate" BETWEEN (start_date::date - INTERVAL '56 days') AND end_date
                        AND "BarBased" = 'Y'
                        AND "Pace" = 'PACE'
                        AND "Status" IN ('I', 'R', 'O')
                    GROUP BY
                        "AsOfDate",
                        "StayDate"
                );

                UPDATE temp_forcast_r28 
                SET "OTB" = (
                    SELECT SUM("OTB") 
                    FROM temp_intermediate
                    WHERE temp_forcast_r28."StayDate" = temp_intermediate."StayDate"
                );

                UPDATE temp_forcast_r28 
                SET "8 Week Rolling AVG" = (
                    SELECT ROUND(AVG("OTB"))
                    FROM temp_intermediate
                    WHERE temp_intermediate."StayDate" IN (
                        (temp_forcast_r28."StayDate"::date - INTERVAL '7 days'), 
                        (temp_forcast_r28."StayDate"::date - INTERVAL '14 days'), 
                        (temp_forcast_r28."StayDate"::date - INTERVAL '21 days'),
                        (temp_forcast_r28."StayDate"::date - INTERVAL '28 days'),
                        (temp_forcast_r28."StayDate"::date - INTERVAL '35 days'),
                        (temp_forcast_r28."StayDate"::date - INTERVAL '42 days'),
                        (temp_forcast_r28."StayDate"::date - INTERVAL '49 days'),
                        (temp_forcast_r28."StayDate"::date - INTERVAL '56 days')
                    )
                    LIMIT 1
                );

            END $$;
        """)

        # Execute the PL/pgSQL block
        conn.execute(bar_based_stats_proc, {
            "property_code": PROPERTY_CODE,
            "start_date": start_date,
            "end_date": end_date,
            "as_of_date": as_of_date
        })

        # Step 2: Fetch data from temp table
        bar_based_stats_query = text("""
            SELECT
                CAST("AsOfDate" AS TEXT),
                CAST("StayDate" AS TEXT),
                COALESCE("OTB", 0) AS "OTB",
                COALESCE("8 Week Rolling AVG", 0) AS "8 Week Rolling AVG"
            FROM temp_forcast_r28;
        """)

        # Fetch and return results
        bar_based_stats_json = fetch_data(conn, bar_based_stats_query, {})

        # 🚀 Rateshop Query
        rateshop_query = text("""
            SELECT 
                rp.competiterpropertyname,
                trs."DayOfWeek",
                trs."Rate",
                trs."Channel",
                trs."IsLowestRate",
                trs."IsBarRate",
                CAST(trs."AsOfDate" AS TEXT) AS "AsOfDate",
                CAST(trs."CheckInDate" AS TEXT) AS "CheckInDate",
                AVG(trs."Rate") OVER (
                    PARTITION BY trs."CompetitorID", trs."CheckInDate"
                ) AS "Competitor_Avg_Rate"
            FROM 
                rs_history_rate_shop trs 
            LEFT JOIN
                rev_propertycompetiters rp 
                ON rp.competiterpropertycode = CAST(trs."CompetitorID" AS TEXT) 
            WHERE
                trs."PropertyCode" = :property_code
                AND trs."AsOfDate" = :as_of_date
                AND trs."CheckInDate" BETWEEN :start_date AND :end_date
                AND trs."Channel" = 'Brand'
            ORDER BY 
                trs."CheckInDate", rp.competiterpropertyname
        """)

        rateshop_json = fetch_data(conn, rateshop_query, {
            "property_code": PROPERTY_CODE,
            "as_of_date": as_of_date,
            "start_date": start_date,
            "end_date": end_date
        })


        # 🚀 One-Day Pickup Query
        one_day_pickup_query = text("""
            SELECT 
                sub1."AsOfDate",
                sub1."Dates",
                (sub1."OTB1" - sub2."OTB2") AS "RMS",
                CAST(round((sub1."TotalRevenue1" - sub2."TotalRevenue2")) as INTEGER) AS "REV",
                CASE 
                    WHEN (sub1."OTB1" - sub2."OTB2") <> 0 AND (sub1."TotalRevenue1" - sub2."TotalRevenue2") <> 0 THEN
                        CAST(round((sub1."TotalRevenue1" - sub2."TotalRevenue2") / (sub1."OTB1" - sub2."OTB2")) as INTEGER) 
                    ELSE 0
                END AS "ADR"
            FROM (
                SELECT 
                    CAST("AsOfDate" as TEXT),
                    CAST("Dates" as TEXT),
                    "RoomSold" as "OTB1",
                    "TotalRevenue" as "TotalRevenue1" 
                FROM dailydata_transaction
                WHERE
                    "AsOfDate" = :as_of_date
                    AND "propertyCode" = :property_code
                    AND "Dates" BETWEEN :start_date AND :end_date
            ) sub1
            LEFT JOIN (
                SELECT 
                    CAST("AsOfDate" as TEXT),
                    CAST("Dates" as TEXT),
                    "RoomSold" as "OTB2",
                    "TotalRevenue" as "TotalRevenue2" 
                FROM dailydata_transaction
                WHERE
                    "AsOfDate" = :pickup_date
                    AND "propertyCode" = :property_code
                    AND "Dates" BETWEEN :start_date AND :end_date
            ) sub2 ON sub1."Dates" = sub2."Dates"
        """)

        one_day_pickup_json = fetch_data(conn, one_day_pickup_query, {
            "as_of_date": as_of_date,
            "property_code": PROPERTY_CODE,
            "start_date": start_date,
            "end_date": end_date,
            "pickup_date": pickup_date
        })


        # 🚀 Seven-Day Pickup Query
        seven_day_pickup_query = text("""
            SELECT 
                sub1."AsOfDate",
                sub1."Dates",
                (sub1."OTB1" - sub2."OTB2") AS "RMS",
                CAST(round((sub1."TotalRevenue1" - sub2."TotalRevenue2")) as INTEGER) AS "REV",
                CASE 
                    WHEN (sub1."OTB1" - sub2."OTB2") <> 0 AND (sub1."TotalRevenue1" - sub2."TotalRevenue2") <> 0 THEN
                        CAST(round((sub1."TotalRevenue1" - sub2."TotalRevenue2") / (sub1."OTB1" - sub2."OTB2")) as INTEGER) 
                    ELSE 0
                END AS "ADR"
            FROM (
                SELECT 
                    CAST("AsOfDate" as TEXT),
                    CAST("Dates" as TEXT),
                    "RoomSold" as "OTB1",
                    "TotalRevenue" as "TotalRevenue1" 
                FROM dailydata_transaction
                WHERE
                    "AsOfDate" = :as_of_date
                    AND "propertyCode" = :property_code
                    AND "Dates" BETWEEN :start_date AND :end_date
            ) sub1
            LEFT JOIN (
                SELECT 
                    CAST("AsOfDate" as TEXT),
                    CAST("Dates" as TEXT),
                    "RoomSold" as "OTB2",
                    "TotalRevenue" as "TotalRevenue2" 
                FROM dailydata_transaction
                WHERE
                    "AsOfDate" = :seven_day_pickup_date
                    AND "propertyCode" = :property_code
                    AND "Dates" BETWEEN :start_date AND :end_date
            ) sub2 ON sub1."Dates" = sub2."Dates"
        """)

        seven_day_pickup_json = fetch_data(conn, seven_day_pickup_query, {
            "as_of_date": as_of_date,
            "property_code": PROPERTY_CODE,
            "start_date": start_date,
            "end_date": end_date,
            "seven_day_pickup_date": seven_day_pickup_date
        })

        # Step 1: Execute the PL/pgSQL block (without returning results)
        pricing_forecast_proc = text("""
            DO $$ 
            DECLARE
                propertycode text := :property_code;
                start_date DATE := :start_date;
                end_date DATE := :end_date;
                asofdate DATE := :as_of_date;
            BEGIN
                DROP TABLE IF EXISTS temp_forcast_r28;   
                CREATE TEMP TABLE temp_forcast_r28 AS 
                SELECT
                    asofdate AS "AsOfDate",
                    generate_series(
                        start_date,
                        end_date,
                        interval '1 DAY'
                    )::date AS "Dates",
                    0 AS "RMS",
                    0 AS "R28AVG",
                    0 AS "Optimal Bar"; 
                
                DROP TABLE IF EXISTS temp_intermediate;
                CREATE TEMP TABLE temp_intermediate AS (
                    SELECT
                        "AsOfDate",
                        "Dates",
                        "RoomSold",
                        ROUND("ADR") AS "ADR"
                    FROM dailydata_transaction
                    WHERE
                        "propertyCode" = propertycode 
                        AND "AsOfDate" = asofdate
                        AND "Dates" BETWEEN start_date AND end_date
                );

                DROP TABLE IF EXISTS temp_intermediate2;
                CREATE TEMP TABLE temp_intermediate2 AS (
                    SELECT
                        "AsOfDate",
                        "Date",
                        "Occupancy",
                        ROUND("Rate") AS "Rate"
                    FROM snp_dbd_forecast
                    WHERE
                        "propertyCode" = propertycode 
                        AND "AsOfDate" = asofdate
                        AND "Date" BETWEEN start_date AND end_date
                );

                UPDATE temp_forcast_r28 SET "RMS" = (
                    SELECT "RoomSold"
                    FROM temp_intermediate
                    WHERE temp_intermediate."Dates" = temp_forcast_r28."Dates" LIMIT 1
                ) WHERE "Dates" < asofdate;

                UPDATE temp_forcast_r28 SET "RMS" = (
                    SELECT "Occupancy"
                    FROM temp_intermediate2
                    WHERE temp_intermediate2."Date" = temp_forcast_r28."Dates" LIMIT 1
                ) WHERE "Dates" >= asofdate;

                UPDATE temp_forcast_r28 SET "Optimal Bar" = (
                    SELECT "ADR"
                    FROM temp_intermediate
                    WHERE temp_intermediate."Dates" = temp_forcast_r28."Dates" LIMIT 1
                ) WHERE "Dates" < asofdate;

                UPDATE temp_forcast_r28 SET "Optimal Bar" = (
                    SELECT ROUND("Rate")
                    FROM temp_intermediate2
                    WHERE temp_intermediate2."Date" = temp_forcast_r28."Dates" LIMIT 1
                ) WHERE "Dates" >= asofdate;

                UPDATE temp_forcast_r28 SET "R28AVG" = (
                    SELECT ROUND(AVG("RoomSold"))
                    FROM dailydata_transaction
                    WHERE "AsOfDate" = asofdate
                    AND "Dates" IN (
                        (temp_forcast_r28."Dates"::date - INTERVAL '7 days'),
                        (temp_forcast_r28."Dates"::date - INTERVAL '14 days'),
                        (temp_forcast_r28."Dates"::date - INTERVAL '21 days'),
                        (temp_forcast_r28."Dates"::date - INTERVAL '28 days')
                    )
                ) WHERE "Dates" <= asofdate + INTERVAL '6 days';

                -- Handle data after asofdate + 6 days
                DROP TABLE IF EXISTS temp_forcast_r28_after_asofdate_plus_day;
                CREATE TEMP TABLE temp_forcast_r28_after_asofdate_plus_day AS 
                SELECT
                    asofdate AS "AsOfDate",
                    generate_series(
                        asofdate,
                        asofdate + INTERVAL '6 days',
                        INTERVAL '1 DAY'
                    )::date AS "Dates", 0 AS "R28AVG";

                UPDATE temp_forcast_r28_after_asofdate_plus_day SET "R28AVG" = (
                    SELECT ROUND(AVG("RoomSold"))
                    FROM dailydata_transaction
                    WHERE "AsOfDate" = asofdate
                    AND "Dates" IN (
                        (temp_forcast_r28_after_asofdate_plus_day."Dates"::date - INTERVAL '7 days'),
                        (temp_forcast_r28_after_asofdate_plus_day."Dates"::date - INTERVAL '14 days'),
                        (temp_forcast_r28_after_asofdate_plus_day."Dates"::date - INTERVAL '21 days'),
                        (temp_forcast_r28_after_asofdate_plus_day."Dates"::date - INTERVAL '28 days')
                    )
                ) WHERE "Dates" <= asofdate + INTERVAL '6 days';

                UPDATE temp_forcast_r28 SET "R28AVG" = temp_forcast_r28_after_asofdate_plus_day."R28AVG"
                FROM temp_forcast_r28_after_asofdate_plus_day
                WHERE TO_CHAR(temp_forcast_r28."Dates", 'Day') = TO_CHAR(temp_forcast_r28_after_asofdate_plus_day."Dates", 'Day')
                AND temp_forcast_r28."Dates" > asofdate + INTERVAL '6 days';

            END $$;
        """)

        # Execute the PL/pgSQL block
        conn.execute(pricing_forecast_proc, {
            "property_code": PROPERTY_CODE,
            "start_date": start_date,
            "end_date": end_date,
            "as_of_date": as_of_date
        })

        # Step 2: Fetch data from temp table
        pricing_forecast_query = text("""
            SELECT *,
                TO_CHAR("AsOfDate", 'YYYY-MM-DD') AS "AsOfDate",
                TO_CHAR("Dates", 'YYYY-MM-DD') AS "Dates"
            FROM temp_forcast_r28;
        """)

        # Fetch results safely
        pricing_forecast_json = fetch_data(conn, pricing_forecast_query, {})

        response_json = {
            "Transient_Current_Year": transient_current_year_json,
            "Bar_Based_Stats": bar_based_stats_json,
            "One_Day_Pickup": one_day_pickup_json,
            "Seven_Day_Pickup": seven_day_pickup_json,
            "Pricing_Forecast": pricing_forecast_json,
            "Rate_Shop": rateshop_json
        }
        
        # print("Response JSON:", response_json)

        check_data(response_json, componentname, AS_OF_DATE, PROPERTY_CODE, CLIENT_ID, db_connection_string)

        return
    except Exception as e:
        err_msg = f"Error : {str(e)}"
        traceback_info = traceback.format_exc()
        print(f"{err_msg}\nTraceback:\n{traceback_info}")
        return None, {"status_code": 0, "message": "Error fetching data", "error": str(e)}

def get_SegmentDrillDown(PROPERTY_CODE, AS_OF_DATE, CLIENT_ID, year, conn, componentname):
    try:
        # Compute dynamic start and end dates
        left_start_date, left_end_date = get_month_start_end_dates(AS_OF_DATE)
        right_start_date, right_end_date = get_month_start_end_dates(AS_OF_DATE, -1)
        last_year_as_of_date = (datetime.strptime(AS_OF_DATE, "%Y-%m-%d") - timedelta(days=365)).strftime("%Y-%m-%d")

        left_market_segment = get_market_seg_room_type(PROPERTY_CODE, conn)[0]
        left_room_type = get_market_seg_room_type(PROPERTY_CODE, conn)[1]


        #unnecessary but why not!!
        right_market_segment = left_market_segment
        right_room_type = left_room_type  

        # Format the query with dynamic values
        reservation_comparison_query = f"""
            DO $$ 
            BEGIN
                -- Left Table
                DROP TABLE IF EXISTS temp_copy_mst_reservation_left;
                CREATE TEMP TABLE temp_copy_mst_reservation_left AS
                SELECT
                    "AsOfDate",
                    "propertyCode",
                    "StayDate",
                    "Status",
                    "BookingDate",
                    "MarketSegment" AS "left_marketsegment",
                    "RoomType",
                    "LeadTime",
                    "LOS",
                    "RoomNight",
                    "Rate" AS "Revenue"
                FROM copy_mst_reservation cmr
                WHERE "AsOfDate" = '{AS_OF_DATE}'
                AND "propertyCode" = '{PROPERTY_CODE}'
                AND "StayDate" BETWEEN '{left_start_date}' AND '{left_end_date}'
                AND EXTRACT(DOW FROM "StayDate") IN (0,1,2,3,4,5,6)
                AND "Status" IN ('I', 'O', 'R')
                AND POSITION(',' || "MarketSegment" || ',' IN ',' || '{left_market_segment}' || ',') > 0
                AND POSITION(',' || "RoomType" || ',' IN ',' || '{left_room_type}' || ',') > 0
                AND "LeadTime" >= -1
                AND "LOS" >= 0;

                -- Right Table
                DROP TABLE IF EXISTS temp_copy_mst_reservation_right;
                CREATE TEMP TABLE temp_copy_mst_reservation_right AS
                SELECT
                    "AsOfDate",
                    "propertyCode",
                    "StayDate",
                    "Status",
                    "BookingDate",
                    "MarketSegment" AS "right_marketsegment",
                    "RoomType",
                    "LeadTime",
                    "LOS",
                    "RoomNight",
                    "Rate" AS "Revenue"
                FROM copy_mst_reservation cmr
                WHERE "AsOfDate" = '{AS_OF_DATE}'
                AND "propertyCode" = '{PROPERTY_CODE}'
                AND "StayDate" BETWEEN '{right_start_date}' AND '{right_end_date}'
                AND EXTRACT(DOW FROM "StayDate") IN (0,1,2,3,4,5,6)
                AND "Status" IN ('I', 'O', 'R')
                AND POSITION(',' || "MarketSegment" || ',' IN ',' || '{right_market_segment}' || ',') > 0
                AND POSITION(',' || "RoomType" || ',' IN ',' || '{right_room_type}' || ',') > 0
                AND "LeadTime" >= -1
                AND "LOS" >= 0;

                -- STLY Table (Same Time Last Year)
                DROP TABLE IF EXISTS temp_copy_mst_reservation_stly;
                CREATE TEMP TABLE temp_copy_mst_reservation_stly AS
                SELECT
                    "AsOfDate",
                    "propertyCode",
                    "StayDate",
                    "Status",
                    "BookingDate",
                    "MarketSegment" AS "stly_marketsegment",
                    "RoomType",
                    "LeadTime",
                    "LOS",
                    "RoomNight",
                    "Rate" AS "Revenue"
                FROM copy_mst_reservation cmr
                WHERE "AsOfDate" = '{AS_OF_DATE}'
                AND "propertyCode" = '{PROPERTY_CODE}'
                AND "StayDate" BETWEEN '{left_start_date}'::date - INTERVAL '1 year' AND '{left_end_date}'::date - INTERVAL '1 year'
                AND EXTRACT(DOW FROM "StayDate") IN (0,1,2,3,4,5,6)
                AND "Status" IN ('I', 'O', 'R')
                AND POSITION(',' || "MarketSegment" || ',' IN ',' || '{left_market_segment}' || ',') > 0
                AND POSITION(',' || "RoomType" || ',' IN ',' || '{left_room_type}' || ',') > 0
                AND "LeadTime" >= -1
                AND "LOS" >= 0
                AND "BookingDate" <= '{last_year_as_of_date}';

                -- Final Data Table
                DROP TABLE IF EXISTS temp_finaldata;
                CREATE TEMP TABLE temp_finaldata AS   
                SELECT
                    '{AS_OF_DATE}'::DATE AS "AsOfDate",
                    COALESCE(ft."left_marketsegment", st."right_marketsegment", tt."stly_marketsegment") AS "marketsegment",
                    SUM(ft."left_RMS") AS "left_RMS",
                    SUM(ft."left_REV") AS "left_REV",
                    SUM(ft."left_ADR") AS "left_ADR",
                    SUM(st."right_RMS") AS "right_RMS",
                    SUM(st."right_REV") AS "right_REV",
                    SUM(st."right_ADR") AS "right_ADR",
                    SUM(tt."stly_RMS") AS "stly_RMS",
                    SUM(tt."stly_REV") AS "stly_REV",
                    SUM(tt."stly_ADR") AS "stly_ADR"
                FROM (
                    SELECT
                        "propertyCode",
                        "left_marketsegment",
                        SUM("RoomNight") AS "left_RMS",
                        ROUND(SUM("Revenue")) AS "left_REV",
                        ROUND(SUM("Revenue") / NULLIF(SUM("RoomNight"), 0), 2) AS "left_ADR"
                    FROM temp_copy_mst_reservation_left 
                    GROUP BY "left_marketsegment", "propertyCode"
                ) ft
                FULL JOIN (
                    SELECT
                        "propertyCode",
                        "right_marketsegment",
                        SUM("RoomNight") AS "right_RMS",
                        ROUND(SUM("Revenue")) AS "right_REV",
                        ROUND(SUM("Revenue") / NULLIF(SUM("RoomNight"), 0), 2) AS "right_ADR"
                    FROM temp_copy_mst_reservation_right 
                    GROUP BY "right_marketsegment", "propertyCode"
                ) st
                ON ft."left_marketsegment" = st."right_marketsegment"
                FULL JOIN (
                    SELECT
                        "propertyCode",
                        "stly_marketsegment",
                        SUM("RoomNight") AS "stly_RMS",
                        ROUND(SUM("Revenue")) AS "stly_REV",
                        ROUND(SUM("Revenue") / NULLIF(SUM("RoomNight"), 0), 2) AS "stly_ADR"
                    FROM temp_copy_mst_reservation_stly 
                    GROUP BY "stly_marketsegment", "propertyCode"
                ) tt
                ON COALESCE(ft."left_marketsegment", st."right_marketsegment") = tt."stly_marketsegment"
                GROUP BY "marketsegment"
                ORDER BY "marketsegment";
            END $$;
        """

        # Execute query inside a transaction
        conn.execute(text(reservation_comparison_query))

        # Fetch Final Data within the same session
        query_final_data = "SELECT * FROM temp_finaldata;"
        ms_data = fetch_data(conn, query_final_data)


        response_json = {
            "market_segment": ms_data
        }

        def round_response_values(response_json):
            for segment in response_json["market_segment"]:
                for key, value in segment.items():
                    if isinstance(value, (float, int)):  # Check if the value is numeric
                        segment[key] = round(value) if value is not None else None  # Round only if it's not None
            return response_json

        rounded_response = round_response_values(response_json)
        # rounded_response = json.dumps(rounded_response, ensure_ascii=False, indent=2)
        print("Response JSON:", rounded_response)

        check_data(rounded_response, componentname, AS_OF_DATE, PROPERTY_CODE, CLIENT_ID, db_connection_string)

        return rounded_response

    except Exception as e:
        err_msg = f"Error fetching segment drilldown data: {str(e)}"
        traceback_info = traceback.format_exc()
        print(f"{err_msg}\nTraceback:\n{traceback_info}")
        return None, {"status_code": 0, "message": "Error fetching data", "error": str(e)}

def get_SeasonalityAnalysis(PROPERTY_CODE, AS_OF_DATE, CLIENT_ID, year, conn, componentname):
    try:
        years = [year - i for i in range(5)]

        seasonality_query = f"""
        SELECT
            "propertyCode",
            CAST("AsOfDate" AS TEXT),
            "year",
            "month",
            CAST("occ" AS INTEGER),
            "rms" AS rms,
            CAST("adr" AS INTEGER),
            CAST("rev" AS INTEGER)
        FROM
            snp_annsmry_on_the_book
        WHERE
            "year" IN ({', '.join(map(str, years))})
            AND "propertyCode" = '{PROPERTY_CODE}'
            AND "AsOfDate" = '{AS_OF_DATE}';
    """
        
        seasonality_data = fetch_data(conn, seasonality_query)

        response_json = {
            "seasonality": seasonality_data
        }

        # print("Response JSON:", response_json)

        check_data(response_json, componentname, AS_OF_DATE, PROPERTY_CODE, CLIENT_ID, db_connection_string)

        return response_json

    except Exception as e:
        err_msg = f"Error : {str(e)}"
        traceback_info = traceback.format_exc()
        print(f"{err_msg}\nTraceback:\n{traceback_info}")
        return None, {"status_code": 0, "message": "Error fetching data", "error": str(e)}
    
def get_AnnCancellationSummary(PROPERTY_CODE, AS_OF_DATE, CLIENT_ID, year, conn, componentname):
    try:
        past_year = year - 1
        last_year_as_of_date = (datetime.strptime(AS_OF_DATE, "%Y-%m-%d") - timedelta(days=365)).strftime("%Y-%m-%d")

        cancellation_cy_query = f"""
            SELECT
            CAST("AsOfDate" AS TEXT),
            TRIM("month") AS "MonthName",
            "rms" AS "CancelledNights",
            ROUND("adr") AS "ADR",
            ROUND("rev") AS "TotalLoss",
            ROUND("occ", 2) AS "CancelledRatio",
            "inv" AS "Total Inventory",
            "avgleadtime" AS "AvgLeadTime",
            "unsoldrms" AS "UnSoldRoom"
        FROM
            snp_annsmry_cancellation
        WHERE
            "propertyCode" = '{PROPERTY_CODE}'
            AND "AsOfDate" = '{AS_OF_DATE}'
            AND "year" = '{year}';
        """

        cancellation_cy_data = fetch_data(conn, cancellation_cy_query)

        cancellation_ly_query = f"""
            SELECT
            CAST("AsOfDate" AS TEXT),
            TRIM("month") AS "MonthName",
            "rms" AS "CancelledNights",
            ROUND("adr") AS "ADR",
            ROUND("rev") AS "TotalLoss",
            ROUND("occ", 2) AS "CancelledRatio",
            "inv" AS "TotalInventory"
            FROM
                snp_annsmry_cancellation
            WHERE
                "propertyCode" = '{PROPERTY_CODE}'
                AND "AsOfDate" = '{AS_OF_DATE}'
                AND "year" = '{past_year}';
        """

        cancellation_ly_data = fetch_data(conn, cancellation_ly_query)

        cancellation_stly_query = f"""
            SELECT
            CAST("AsOfDate" AS TEXT),
            TRIM("month") AS "MonthName",
            "rms" AS "CancelledNights",
            ROUND("adr") AS "ADR",
            ROUND("rev") AS "TotalLoss",
            ROUND("occ", 2) AS "CancelledRatio",
            "inv" AS "TotalInventory"
            FROM
                snp_annsmry_cancellation
            WHERE
                "propertyCode" = '{PROPERTY_CODE}'
                AND "AsOfDate" = '{last_year_as_of_date}'
                AND "year" = '{past_year}';
        """

        cancellation_stly_data = fetch_data(conn, cancellation_stly_query)

        cancellation_monthly_pace_query = f"""
                SELECT
                TRIM("Month") AS "MonthName",
                SUM(CP_LIST."CP0") AS "CP0",
                SUM(CP_LIST."CP1") AS "CP1",
                SUM(CP_LIST."CP2TO7") AS "CP2TO7",
                SUM(CP_LIST."CP8TO15") AS "CP8TO15",
                SUM(CP_LIST."CP16TO30") AS "CP16TO30",
                SUM(CP_LIST."CP31TO60") AS "CP31TO60",
                SUM(CP_LIST."CP61TO90") AS "CP61TO90",
                SUM(CP_LIST."CP91TOUP") AS "CP91TOUP",

                ROUND(SUM(CP_LIST."CP0_REV")) AS "CP0_REV",
                ROUND(SUM(CP_LIST."CP1_REV")) AS "CP1_REV",
                ROUND(SUM(CP_LIST."CP2TO7_REV")) AS "CP2TO7_REV",
                ROUND(SUM(CP_LIST."CP8TO15_REV")) AS "CP8TO15_REV",
                ROUND(SUM(CP_LIST."CP16TO30_REV")) AS "CP16TO30_REV",
                ROUND(SUM(CP_LIST."CP31TO60_REV")) AS "CP31TO60_REV",
                ROUND(SUM(CP_LIST."CP61TO90_REV")) AS "CP61TO90_REV",
                ROUND(SUM(CP_LIST."CP91TOUP_REV")) AS "CP91TOUP_REV",

                CASE
                    WHEN SUM(CP_LIST."CP0") <> 0 THEN ROUND((ROUND(SUM(CP_LIST."CP0_REV")) / SUM(CP_LIST."CP0")))
                    ELSE 0
                END AS "CP0_ADR",
                CASE
                    WHEN SUM(CP_LIST."CP1") <> 0 THEN ROUND((ROUND(SUM(CP_LIST."CP1_REV")) / SUM(CP_LIST."CP1")))
                    ELSE 0
                END AS "CP1_ADR",
                CASE
                    WHEN SUM(CP_LIST."CP2TO7") <> 0 THEN ROUND((ROUND(SUM(CP_LIST."CP2TO7_REV")) / SUM(CP_LIST."CP2TO7")))
                    ELSE 0
                END AS "CP2TO7_ADR",
                CASE
                    WHEN SUM(CP_LIST."CP8TO15") <> 0 THEN ROUND((ROUND(SUM(CP_LIST."CP8TO15_REV")) / SUM(CP_LIST."CP8TO15")))
                    ELSE 0
                END AS "CP8TO15_ADR",
                CASE
                    WHEN SUM(CP_LIST."CP16TO30") <> 0 THEN ROUND((ROUND(SUM(CP_LIST."CP16TO30_REV")) / SUM(CP_LIST."CP16TO30")))
                    ELSE 0
                END AS "CP16TO30_ADR",
                CASE
                    WHEN SUM(CP_LIST."CP31TO60") <> 0 THEN ROUND((ROUND(SUM(CP_LIST."CP31TO60_REV")) / SUM(CP_LIST."CP31TO60")))
                    ELSE 0
                END AS "CP31TO60_ADR",
                CASE
                    WHEN SUM(CP_LIST."CP61TO90") <> 0 THEN ROUND((ROUND(SUM(CP_LIST."CP61TO90_REV")) / SUM(CP_LIST."CP61TO90")))
                    ELSE 0
                END AS "CP61TO90_ADR",
                CASE
                    WHEN SUM(CP_LIST."CP91TOUP") <> 0 THEN ROUND((ROUND(SUM(CP_LIST."CP91TOUP_REV")) / SUM(CP_LIST."CP91TOUP")))
                    ELSE 0
                END AS "CP91TOUP_ADR"

            FROM (
                SELECT
                    TO_CHAR("StayDate", 'month') AS "Month",
                    CASE WHEN ("ArrivalDate" - "CancellationDate") = 0 THEN 1 ELSE 0 END AS "CP0",
                    CASE WHEN ("ArrivalDate" - "CancellationDate") = 1 THEN 1 ELSE 0 END AS "CP1",
                    CASE WHEN ("ArrivalDate" - "CancellationDate") BETWEEN 2 AND 7 THEN 1 ELSE 0 END AS "CP2TO7",
                    CASE WHEN ("ArrivalDate" - "CancellationDate") BETWEEN 8 AND 15 THEN 1 ELSE 0 END AS "CP8TO15",
                    CASE WHEN ("ArrivalDate" - "CancellationDate") BETWEEN 16 AND 30 THEN 1 ELSE 0 END AS "CP16TO30",
                    CASE WHEN ("ArrivalDate" - "CancellationDate") BETWEEN 31 AND 60 THEN 1 ELSE 0 END AS "CP31TO60",
                    CASE WHEN ("ArrivalDate" - "CancellationDate") BETWEEN 61 AND 90 THEN 1 ELSE 0 END AS "CP61TO90",
                    CASE WHEN ("ArrivalDate" - "CancellationDate") >= 91 THEN 1 ELSE 0 END AS "CP91TOUP",

                    CASE WHEN ("ArrivalDate" - "CancellationDate") = 0 THEN "Rate" ELSE 0 END AS "CP0_REV",
                    CASE WHEN ("ArrivalDate" - "CancellationDate") = 1 THEN "Rate" ELSE 0 END AS "CP1_REV",
                    CASE WHEN ("ArrivalDate" - "CancellationDate") BETWEEN 2 AND 7 THEN "Rate" ELSE 0 END AS "CP2TO7_REV",
                    CASE WHEN ("ArrivalDate" - "CancellationDate") BETWEEN 8 AND 15 THEN "Rate" ELSE 0 END AS "CP8TO15_REV",
                    CASE WHEN ("ArrivalDate" - "CancellationDate") BETWEEN 16 AND 30 THEN "Rate" ELSE 0 END AS "CP16TO30_REV",
                    CASE WHEN ("ArrivalDate" - "CancellationDate") BETWEEN 31 AND 60 THEN "Rate" ELSE 0 END AS "CP31TO60_REV",
                    CASE WHEN ("ArrivalDate" - "CancellationDate") BETWEEN 61 AND 90 THEN "Rate" ELSE 0 END AS "CP61TO90_REV",
                    CASE WHEN ("ArrivalDate" - "CancellationDate") >= 91 THEN "Rate" ELSE 0 END AS "CP91TOUP_REV"

                FROM copy_mst_reservation
                WHERE "propertyCode" = '{PROPERTY_CODE}'
                    AND "AsOfDate" = '{AS_OF_DATE}'
                    AND "Status" IN ('C')
                    AND TO_CHAR("StayDate", 'yyyy') = '{year}'
                    AND TO_CHAR("StayDate", 'mm') BETWEEN '01' AND '12'
            ) CP_LIST
            GROUP BY "Month";
        """

        cancellation_monthly_pace_data = fetch_data(conn, cancellation_monthly_pace_query)

        response_json = {
            "cancellation_cy": cancellation_cy_data,
            "cancellation_ly": cancellation_ly_data,
            "cancellation_stly": cancellation_stly_data,
            "cancellation_monthly_pace": cancellation_monthly_pace_data
        }

        check_data(response_json, componentname, AS_OF_DATE, PROPERTY_CODE, CLIENT_ID, db_connection_string)

    except Exception as e:
        err_msg = f"Error : {str(e)}"
        traceback_info = traceback.format_exc()
        print(f"{err_msg}\nTraceback:\n{traceback_info}")
        return None, {"status_code": 0, "message": "Error fetching data", "error": str(e)}

def get_client_ids(conn_str):
    try:
        url = urlparse(conn_str)
        connection = mysql.connector.connect(
            host=url.hostname,
            user=url.username,
            password=url.password,
            database=url.path[1:],  # Removing the leading '/'
        )

        if connection.is_connected():
            query = f"""SELECT clientid FROM mst_client;"""
            cursor = connection.cursor(dictionary=True)
            try:
                cursor.execute(query)
                result = cursor.fetchall()
                client_ids = [client["clientid"] for client in result]
                return client_ids
            except Exception as e:
                print("Error:", e)
                return None
            finally:
                cursor.close()
    except Exception as e:
        err_msg = f"Error : {str(e)}"
        traceback_info = traceback.format_exc()
        print(f"{err_msg}\nTraceback:\n{traceback_info}")
    finally:
        pass

def get_property_codes(CLIENT_ID_LIST, conn_str):
    CLIENT_PROPERTY_LIST = []
    try:
        for CLIENT_ID in CLIENT_ID_LIST:
            config_db_conn = db_config.get_db_connection(PROPERTY_DATABASE='', clientId=CLIENT_ID, connection_string=conn_str)
            if config_db_conn is None:
                print(f"❌ Failed to connect to database for CLIENT_ID: {CLIENT_ID}. Skipping.")
                continue
            else:
                query = text("SELECT propertycode FROM pro_property WHERE isactive = TRUE;")
                try:
                    result = config_db_conn.execute(query)
                    property_codes = [row["propertycode"] for row in result.mappings()]
                    CLIENT_PROPERTY_LIST.extend([[CLIENT_ID, prop] for prop in property_codes])
                except Exception as e:
                    print("Error:", e)
                    return None
                finally:
                    config_db_conn.close()
        return CLIENT_PROPERTY_LIST
    except Exception as e:
        err_msg = f"Error : {str(e)}"
        traceback_info = traceback.format_exc()
        print(f"{err_msg}\nTraceback:\n{traceback_info}")
    finally:
        pass

def main():
    print("Starting")
    # start_time = time.time() 
    
    # CLIENT_ID_LIST = get_client_ids(db_connection_string)
    # print("Client IDs:", CLIENT_ID_LIST)
    # CLIENT_PROPERTY_LIST = get_property_codes(CLIENT_ID_LIST, db_connection_string)
    # print("Client Property List:", CLIENT_PROPERTY_LIST)
    # end_time = time.time()

    # print(f"\nTime taken for finding property codes: {end_time - start_time} seconds")
    start_time = time.time() 
    CLIENT_PROPERTY_LIST = [[6, 'HK_AC32AW']]
    print("Processing Comments for all properties")
    for CLIENT_ID, PROPERTY_CODE in CLIENT_PROPERTY_LIST:

        conn = db_config.get_db_connection(PROPERTY_DATABASE=PROPERTY_CODE, clientId=CLIENT_ID, connection_string=db_connection_string)

        if conn is None:
            print(f"❌ Failed to connect to database for {PROPERTY_CODE}. Skipping.")
            return

        print(f"Processing Comments for Property Code: {PROPERTY_CODE}")
        AS_OF_DATE, year = get_asofdate(PROPERTY_CODE, conn)

        if AS_OF_DATE is not None and year is not None:
            widget_list = [
                        # "AnnualSummary", 
                        # "ForecastCommon", 
                        # "PickupCommon",
                        # "SegmentDrillDown",
                        # "ORG",
                        # "SeasonalityAnalysis",
                        "AnnCancellationSummary",
                        ]
            
            for widget in widget_list:
                function_name = f"get_{widget}" 

                if function_name in globals():
                    print(f"Fetching {widget} data and Generating Comments")
                    globals()[function_name](PROPERTY_CODE, AS_OF_DATE, CLIENT_ID, year, conn, widget)
                    print(f"✅ {function_name} executed successfully:")
                else:
                    print(f"❌ Function {function_name} not found.")
        else:
            print(f"❌ Error: AS_OF_DATE or year is None. Skipping.")
            continue

        if conn is not None:
            print("Closing connection")
            conn.close
        
    end_time = time.time()

    

    print(f"\nTime taken: {end_time - start_time} seconds")

if __name__ == "__main__":
    main()
