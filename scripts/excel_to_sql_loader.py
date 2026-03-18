import os
import pandas as pd
import pyodbc
from dotenv import load_dotenv

# =========================
# LOAD ENV
# =========================
ENV_PATH = r"K:\Kmis_Public\Clare\rms_lookup_app\.env"
load_dotenv(dotenv_path=ENV_PATH)

MSSQL_SERVER = os.getenv("MSSQL_SERVER")
MSSQL_DATABASE = os.getenv("MSSQL_DATABASE")

if not MSSQL_SERVER or not MSSQL_DATABASE:
    raise Exception("Missing MSSQL_SERVER or MSSQL_DATABASE")

# =========================
# SQL CONNECTION
# =========================
def get_mssql_conn():
    conn_str = (
        f"DRIVER={{ODBC Driver 17 for SQL Server}};"
        f"SERVER={MSSQL_SERVER};"
        f"DATABASE={MSSQL_DATABASE};"
        "Trusted_Connection=yes;"
    )
    return pyodbc.connect(conn_str)

# =========================
# FILE PATH
# =========================
INPUT_FILE = r"C:\Users\XDong\OneDrive - Hankey Group\Desktop\RMS Risk Output.xlsx"

# =========================
# FORMAT CLEANING
# =========================
def clean_row(row):

    lat = round(float(row["LATITUDE"]), 6)
    lon = round(float(row["LONGITUDE"]), 6)

    street = str(row["STREET"]).upper().strip()
    city = str(row["CITY"]).upper().strip()
    state = str(row["STATE"]).upper().strip()

    county = None
    if pd.notna(row.get("COUNTY")):
        county = str(row["COUNTY"]).upper().strip()

    zip_code = str(row["ZIP CODE"]).strip()

    normalized_address = f"{street}|{city}|{state}|{zip_code}"

    row["LATITUDE"] = lat
    row["LONGITUDE"] = lon
    row["STREET"] = street
    row["CITY"] = city
    row["STATE"] = state
    row["COUNTY"] = county
    row["ZIP CODE"] = zip_code
    row["NormalizedAddress"] = normalized_address

    return row

# =========================
# CHECK EXISTING LOCATION
# =========================
def location_exists(cursor, lat, lon):

    cursor.execute("""
        SELECT 1
        FROM dbo.Moodys_Location_Risk
        WHERE Latitude = ? AND Longitude = ?
    """, (lat, lon))

    return cursor.fetchone() is not None

# =========================
# INSERT LOCATION
# =========================
def insert_location(cursor, row):

    cursor.execute("""
        INSERT INTO dbo.Moodys_Location_Risk (
            Latitude, Longitude,
            Street, City, County, State, ZipCode,
            NormalizedAddress,
            OverallScore, Score100yr, Score250yr, Score500yr,
            BuildingALR, ContentsALR, BusinessInterruptionALR,
            RawResponseJson
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        row["LATITUDE"],
        row["LONGITUDE"],
        row["STREET"],
        row["CITY"],
        row["COUNTY"],
        row["STATE"],
        row["ZIP CODE"],
        row["NormalizedAddress"],
        row["OverallScore"],
        row["Score100yr"],
        row["Score250yr"],
        row["Score500yr"],
        row["BuildingALR"],
        row["ContentsALR"],
        row["BusinessInterruptionALR"],
        row["RawResponseJson"]
    ))

# =========================
# INSERT QUERY HISTORY
# =========================
def insert_query_history(cursor, row):

    cursor.execute("""
        INSERT INTO dbo.Moodys_Query_History (
            LocationRiskId,
            BuildingValue,
            ContentsValue,
            BusinessInterruptionValue,
            BuildingAAL,
            ContentsAAL,
            BusinessInterruptionAAL,
            TotalAAL
        )
        SELECT LocationRiskId, ?, ?, ?, ?, ?, ?, ?
        FROM dbo.Moodys_Location_Risk
        WHERE Latitude = ? AND Longitude = ?
    """, (
        float(row.get("BUILDING VALUE", 0) or 0),
        float(row.get("CONTENTS VALUE", 0) or 0),
        float(row.get("BUSINESS INTERRUPTION VALUE", 0) or 0),
        float(row.get("BuildingAAL", 0) or 0),
        float(row.get("ContentsAAL", 0) or 0),
        float(row.get("BusinessInterruptionAAL", 0) or 0),
        float(row.get("TotalAAL", 0) or 0),
        row["LATITUDE"],
        row["LONGITUDE"]
    ))

# =========================
# MAIN
# =========================
def main():

    df = pd.read_excel(INPUT_FILE)

    conn = get_mssql_conn()
    cursor = conn.cursor()

    total = len(df)
    inserted = 0
    skipped = 0

    for idx, row in df.iterrows():

        row = clean_row(row)

        lat = row["LATITUDE"]
        lon = row["LONGITUDE"]

        if location_exists(cursor, lat, lon):
            print(f"Skipping {idx+1}/{total} - Already Exists")
            skipped += 1
            continue

        print(f"Inserting {idx+1}/{total} - {row['STREET']}")

        insert_location(cursor, row)
        insert_query_history(cursor, row)

        inserted += 1

    conn.commit()
    conn.close()

    print("\n==============================")
    print(f"Inserted: {inserted}")
    print(f"Skipped : {skipped}")
    print("Upload Completed Successfully")
    print("==============================")

if __name__ == "__main__":
    main()
