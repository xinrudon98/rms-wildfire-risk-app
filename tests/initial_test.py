import os
import requests
from dotenv import load_dotenv

# =========================
# LOAD ENV
# =========================
load_dotenv()

RMS_API_KEY = os.getenv("RMS_API_KEY")

if not RMS_API_KEY:
    raise ValueError("Missing RMS_API_KEY in environment variables")

# =========================
# API CONFIG
# =========================
API_URL = "https://api-use1.rms.com/li/composite"

headers = {
    "content-type": "application/json",
    "authorization": RMS_API_KEY
}

# =========================
# TEST REQUEST
# =========================
payload = {
    "location": {
        "address": {
            "admin1Code": "CA",
            "cityName": "NEWARK",
            "countryCode": "US",
            "countryScheme": "ISO2A",
            "postalCode": "94560",
            "streetAddress": "7575 GATEWAY BLVD"
        },
        "characteristics": {
            "construction": "ATC1",
            "occupancy": "ATC1",
            "yearBuilt": 1973,
            "numOfStories": 3,
            "foundationType": 0,
            "basement": "DEFAULT",
            "floorArea": 0
        },
        "coverageValues": {
            "buildingValue": 1000000,
            "contentsValue": 100000,
            "businessInterruptionValue": 5000
        }
    },
    "layers": [
        {"name": "geocode", "version": "latest"},
        {"name": "us_wf_risk_score", "version": "2.0"},
        {"name": "us_wf_loss_cost", "version": "latest"}
    ]
}

# =========================
# RUN TEST
# =========================
def run_test():
    response = requests.post(API_URL, json=payload, headers=headers)

    print("Status Code:", response.status_code)

    try:
        data = response.json()
        print("Response JSON:")
        print(data)
    except Exception:
        print("Raw Response:")
        print(response.text)


if __name__ == "__main__":
    run_test()
