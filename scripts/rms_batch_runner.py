import os
import json
import time
import requests
import pandas as pd
from dotenv import load_dotenv

# =========================
# LOAD ENV
# =========================
ENV_PATH = r"K:\Kmis_Public\Clare\rms_lookup_app\.env"
load_dotenv(dotenv_path=ENV_PATH)

RMS_API_KEY = os.getenv("RMS_API_KEY")
RMS_HOST = os.getenv("RMS_HOST")

if not RMS_API_KEY or not RMS_HOST:
    raise Exception("Missing RMS_API_KEY or RMS_HOST")

# =========================
# FILE PATHS
# =========================
INPUT_FILE = r"C:\Users\XDong\OneDrive - Hankey Group\Desktop\RMS Risk.xlsx"
OUTPUT_FILE = r"C:\Users\XDong\OneDrive - Hankey Group\Desktop\RMS Risk Output.xlsx"

# =========================
# Helper Functions
# =========================
def safe_int(value, default=None):
    if pd.isna(value) or value == "":
        return default
    return int(float(value))

def safe_float(value, default=0.0):
    if pd.isna(value) or value == "":
        return default
    return float(value)

# =========================
# RMS API Call
# =========================
def call_rms_api(row):

    street = row["STREET"]
    city = row["CITY"]
    state = row["STATE"]
    zip_code = str(row["ZIP CODE"])

    building_value = safe_float(row.get("BUILDING VALUE"), 0)
    contents_value = safe_float(row.get("CONTENTS VALUE"), 0)
    bi_value = safe_float(row.get("BUSINESS INTERRUPTION VALUE"), 0)

    year_built = safe_int(row.get("YEAR BUILT"))
    num_stories = safe_int(row.get("NUM OF STORIES"), 1)
    floor_area = safe_float(row.get("SQFT"), 0)

    url = f"{RMS_HOST}/li/composite"

    headers = {
        "content-type": "application/json",
        "authorization": RMS_API_KEY
    }

    payload = {
        "location": {
            "address": {
                "streetAddress": street,
                "cityName": city,
                "admin1Code": state,
                "postalCode": zip_code,
                "countryCode": "US",
                "countryRmsCode": "US",
                "countryScheme": "ISO2A",
                "rmsGeoModelResolutionCode": "2"
            },
            "characteristics": {
                "occupancy": "ATC1",
                "yearBuilt": year_built,
                "numOfStories": num_stories,
                "floorArea": floor_area
            },
            "coverageValues": {
                "buildingValue": building_value,
                "contentsValue": contents_value,
                "businessInterruptionValue": bi_value
            }
        },
        "layers": [
            {"name": "geocode", "version": "latest"},
            {"name": "us_wf_risk_score", "version": "2.0"},
            {"name": "us_wf_loss_cost", "version": "latest"}
        ]
    }

    response = requests.post(url, json=payload, headers=headers)

    if response.status_code >= 400:
        raise Exception(response.text)

    data = response.json()

    geocode_layer = next((x for x in data if x["name"] == "geocode"), {})
    risk_layer = next((x for x in data if x["name"] == "us_wf_risk_score"), {})
    loss_layer = next((x for x in data if x["name"] == "us_wf_loss_cost"), {})

    risk = risk_layer.get("results", {})
    loss = loss_layer.get("results", {})

    building_alr = safe_float(loss.get("buildingAlr"), 0)
    contents_alr = safe_float(loss.get("contentsAlr"), 0)
    bi_alr = safe_float(loss.get("businessInterruptionAlr"), 0)

    building_aal = building_alr * building_value
    contents_aal = contents_alr * contents_value
    bi_aal = bi_alr * bi_value
    total_aal = safe_float(loss.get("groundUpLoss"), 0)

    return {
        "OverallScore": risk.get("scoreOverall"),
        "Score100yr": risk.get("score100yr"),
        "Score250yr": risk.get("score250yr"),
        "Score500yr": risk.get("score500yr"),
        "BuildingALR": building_alr,
        "ContentsALR": contents_alr,
        "BusinessInterruptionALR": bi_alr,
        "BuildingAAL": building_aal,
        "ContentsAAL": contents_aal,
        "BusinessInterruptionAAL": bi_aal,
        "TotalAAL": total_aal,
        "RawResponseJson": json.dumps(data)
    }

# =========================
# Main Runner
# =========================
def main():

    df = pd.read_excel(INPUT_FILE, sheet_name="DATA")

    results = []

    for idx, row in df.iterrows():
        print(f"Processing {idx+1} / {len(df)} - {row['STREET']}")

        try:
            api_result = call_rms_api(row)
            combined = {**row.to_dict(), **api_result}
            results.append(combined)
            time.sleep(0.15)

        except Exception as e:
            print("ERROR:", e)
            combined = row.to_dict()
            combined["Error"] = str(e)
            results.append(combined)

    result_df = pd.DataFrame(results)
    result_df.to_excel(OUTPUT_FILE, index=False)

    print("\n==========================")
    print("Batch Completed")
    print("Saved to:", OUTPUT_FILE)
    print("==========================")

if __name__ == "__main__":
    main()
