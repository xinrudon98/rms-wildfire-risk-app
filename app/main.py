import os
import json
import requests
from typing import Optional
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, StreamingResponse
from pydantic import BaseModel, Field
import pandas as pd
import io
import pyodbc
from dotenv import load_dotenv
load_dotenv()
from datetime import datetime

MSSQL_SERVER = os.getenv("MSSQL_SERVER")
MSSQL_DATABASE = os.getenv("MSSQL_DATABASE")

def get_mssql_conn():
    conn_str = (
        f"DRIVER={{ODBC Driver 17 for SQL Server}};"
        f"SERVER={MSSQL_SERVER};"
        f"DATABASE={MSSQL_DATABASE};"
        "Trusted_Connection=yes;"
    )
    return pyodbc.connect(conn_str)

def insert_location_cache(lat, lon, geo_res, risk_res, loss_res, raw_json, normalized_address):

    conn = get_mssql_conn()
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO dbo.Moodys_Location_Risk (
            NormalizedAddress,
            Latitude, Longitude,
            Street, City, County, State, ZipCode,
            OverallScore, Score100yr, Score250yr, Score500yr,
            BuildingALR, ContentsALR, BusinessInterruptionALR,
            RawResponseJson
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        normalized_address,
        lat, lon,
        geo_res.get("streetAddress"),
        geo_res.get("cityName"),
        geo_res.get("admin2Name"),
        geo_res.get("admin1Code"),
        geo_res.get("postalCode"),
        risk_res.get("scoreOverall"),
        risk_res.get("score100yr"),
        risk_res.get("score250yr"),
        risk_res.get("score500yr"),
        loss_res.get("buildingAlr"),
        loss_res.get("contentsAlr"),
        loss_res.get("businessInterruptionAlr"),
        raw_json
    ))

    conn.commit()
    conn.close()

def query_history_exists(location_id, req):
    conn = get_mssql_conn()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT TOP 1 1
        FROM dbo.Moodys_Query_History
        WHERE LocationRiskId = ?
          AND BuildingValue = ?
          AND ContentsValue = ?
          AND BusinessInterruptionValue = ?
    """, (
        location_id,
        float(req.building_value or 0),
        float(req.contents_value or 0),
        float(req.business_interruption_value or 0)
    ))

    exists = cursor.fetchone()
    conn.close()
    return exists is not None

def insert_query_history(location_id, req, building_alr, contents_alr, bi_alr):
    conn = get_mssql_conn()
    cursor = conn.cursor()

    building_value = float(req.building_value or 0)
    contents_value = float(req.contents_value or 0)
    bi_value = float(req.business_interruption_value or 0)

    building_alr = float(building_alr or 0)
    contents_alr = float(contents_alr or 0)
    bi_alr = float(bi_alr or 0)

    building_aal = building_alr * building_value
    contents_aal = contents_alr * contents_value
    bi_aal = bi_alr * bi_value
    total_aal = building_aal + contents_aal + bi_aal

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
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        location_id,
        building_value,
        contents_value,
        bi_value,
        building_aal,
        contents_aal,
        bi_aal,
        total_aal
    ))

    conn.commit()
    conn.close()

# =========================
# Environment Variables
# =========================
RMS_API_KEY = os.getenv("RMS_API_KEY")
RMS_HOST = os.getenv("RMS_HOST")

if not RMS_API_KEY or not RMS_HOST:
    raise RuntimeError("Missing RMS_API_KEY or RMS_HOST")

# =========================
# FastAPI App
# =========================
app = FastAPI(title="RMS Composite Lookup")
def init_db():
    print("Using existing Supabase table")

# =========================
# Request Model
# =========================
class LookupRequest(BaseModel):
    address: str
    building_value: Optional[int] = Field(0, ge=0)
    contents_value: Optional[int] = Field(0, ge=0)
    business_interruption_value: Optional[int] = Field(0, ge=0)

# =========================
# Address Parser
# =========================
def parse_address(address_str: str):
    try:
        parts = [p.strip() for p in address_str.split(",")]
        street = parts[0]
        city = parts[1]
        state_zip = parts[2].split()
        state = state_zip[0]
        zip_code = state_zip[1]
        return street, city, state, zip_code
    except Exception:
        raise HTTPException(
            status_code=400,
            detail="Address format must be: Street, City, State ZIP"
        )
    
def normalize_address(street, city, state, zip_code):
    return f"{street.strip().upper()}|{city.strip().upper()}|{state.strip().upper()}|{zip_code.strip()}"

def get_location_cache_by_address(normalized_address):
    conn = get_mssql_conn()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT TOP 1
            LocationRiskId,
            Latitude, Longitude,
            Street, City, County, State, ZipCode,
            OverallScore, Score100yr, Score250yr, Score500yr,
            BuildingALR, ContentsALR, BusinessInterruptionALR
        FROM dbo.Moodys_Location_Risk
        WHERE NormalizedAddress = ?
    """, (normalized_address,))
    row = cursor.fetchone()
    conn.close()
    return row

# =========================
# Frontend UI
# =========================
@app.get("/", response_class=HTMLResponse)
def home():
    return """
<!doctype html>
<html>
<head>
<meta charset="utf-8" />
<title>RMS WILDFIRE RISK LOOKUP</title>
<script src="https://unpkg.com/lucide@latest"></script>

<style>
body{
font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Arial;
background:#F2F2F2;
margin:0;
padding:0;
color:#404040;
}

/* HERO */
.hero{
background:#404040;
color:white;
padding:70px 60px;
}

.hero h1{
margin:0;
font-weight:800;
letter-spacing:2px;
font-size:26px;
}

.hero-divider{
height:1px;
background:rgba(255,255,255,0.15);
margin-top:25px;
}

.download-btn{
background:transparent;
border:1px solid rgba(255,255,255,0.3);
color:rgba(255,255,255,0.85);
padding:8px 14px;
border-radius:6px;
font-size:12px;
letter-spacing:0.6px;
cursor:pointer;
transition:all 0.2s ease;
}

.download-btn:hover{
background:rgba(255,255,255,0.08);
border-color:rgba(255,255,255,0.6);
color:white;
}

/* WRAPPER */
.container{
max-width:1200px;
margin:-40px auto 80px auto;
padding:0 40px;
}

/* CARD */
.card{
background:white;
padding:35px;
border-radius:18px;
margin-bottom:40px;
box-shadow:0 12px 35px rgba(0,0,0,0.05);
border:1px solid #EDEDED;
transition:all 0.2s ease;
}

.card:hover{
box-shadow:0 18px 45px rgba(0,0,0,0.06);
}

/* SECTION */
.section-title{
display:flex;
align-items:center;
gap:10px;
font-size:13px;
letter-spacing:1px;
text-transform:uppercase;
color:#595959;
margin-bottom:25px;
}

.section-title svg{
width:18px;
height:18px;
stroke:#8497B0;
}

/* INPUT */
.input-grid{
display:grid;
grid-template-columns:repeat(auto-fit,minmax(220px,1fr));
gap:16px;
}

input{
padding:12px;
border-radius:8px;
border:1px solid #DDD;
background:#FAFAFA;
font-size:14px;
transition:all 0.2s ease;
}

input:focus{
outline:none;
border-color:#8497B0;
box-shadow:0 0 0 3px rgba(132,151,176,0.15);
background:white;
}

button{
margin-top:25px;
padding:14px;
border-radius:8px;
border:none;
background:#8497B0;
color:white;
font-size:14px;
cursor:pointer;
letter-spacing:0.5px;
transition:all 0.2s ease;
}

button:hover{
background:#6D829B;
transform:translateY(-1px);
}

/* METRICS */
.metric{
margin:6px 0;
font-size:14px;
color:#595959;
}

.metric-strong{
font-size:18px;
font-weight:600;
color:#404040;
margin-top:6px;
}

/* RISK */
.risk-wrapper{
background:#EEF1F5;
padding:30px;
border-radius:14px;
margin-top:20px;
}

.risk-grid{
display:grid;
grid-template-columns:repeat(auto-fit,minmax(260px,1fr));
gap:20px;
margin-top:25px;
}

.data-card{
background:white;
padding:24px;
border-radius:12px;
border-left:4px solid #8497B0;
display:flex;
flex-direction:column;
gap:8px;
transition:all 0.2s ease;
}

.data-card:hover{
transform:translateY(-2px);
box-shadow:0 8px 20px rgba(0,0,0,0.05);
}

.summary-section{
margin-top:32px;
border-top:1px solid #E5E5E5;
padding-top:22px;
}

.summary-title{
font-size:13px;
text-transform:uppercase;
letter-spacing:1px;
color:#595959;
}

.summary-value{
font-size:26px;
font-weight:700;
color:#404040;
margin-top:8px;
}

.card-title{
font-size:12px;
text-transform:uppercase;
letter-spacing:1px;
color:#595959;
}

.card-value{
font-size:18px;
font-weight:600;
color:#404040;
}

.card-sub{
font-size:13px;
color:#777;
}

.risk-title{
font-size:13px;
text-transform:uppercase;
letter-spacing:1px;
margin-bottom:12px;
color:#595959;
}

.risk-badge{
padding:6px 14px;
border-radius:999px;
font-weight:600;
color:white;
font-size:14px;
letter-spacing:0.5px;
box-shadow:0 2px 6px rgba(0,0,0,0.15);
}

/* LOSS */
.loss-section{
background:#F7F7F7;
padding:30px;
border-radius:14px;
margin-top:20px;
}

.loss-grid{
display:grid;
grid-template-columns:repeat(auto-fit, minmax(260px, 1fr));
gap:20px;
}

.loss-card{
background:white;
padding:22px;
border-radius:12px;
border-left:4px solid #EEE1B3;
display:flex;
flex-direction:column;
justify-content:space-between;
}

.placeholder{
color:#999;
font-style:italic;
}

/* LOADING */
.loading{
text-align:center;
padding:40px;
color:#595959;
}

.spinner{
width:28px;
height:28px;
border:3px solid #DDD;
border-top:3px solid #8497B0;
border-radius:50%;
animation:spin 0.8s linear infinite;
margin:0 auto 15px auto;
}

@keyframes spin{
0%{transform:rotate(0deg);}
100%{transform:rotate(360deg);}
}

a{
color:#8497B0;
text-decoration:none;
}
a:hover{
text-decoration:underline;
}
</style>
</head>

<body>

<div class="hero">
    <div style="display:flex; justify-content:space-between; align-items:center;">
        <h1>RMS WILDFIRE RISK LOOKUP</h1>
        <button onclick="downloadHistory()" class="download-btn">
            Download History
        </button>
    </div>
    <div class="hero-divider"></div>
</div>

<div class="container">

<div class="card">
<div class="section-title">
<i data-lucide="home"></i>
Property Information
</div>

<div class="input-grid">
<input id="address" placeholder="Street, City, State ZIP"/>
<input id="building_value" type="number" min="0" step="1" placeholder="Building Value"/>
<input id="contents_value" type="number" min="0" step="1" placeholder="Contents Value"/>
<input id="business_interruption_value" type="number" min="0" step="1" placeholder="Business Interruption Value"/>
</div>

<button onclick="lookup()">Run Risk Analysis</button>
</div>

<div id="results"></div>

</div>

<script>
lucide.createIcons();

function getDamageRatio(score){
const map={
1:[0,0.5],
2:[0.5,1],
3:[1,5],
4:[5,10],
5:[10,15],
6:[15,20],
7:[20,30],
8:[30,40],
9:[40,50],
10:[50,75]
};
return map[score]||[0,0];
}

function riskColor(score){
const hue=Math.max(0,120-(score*10));
return `hsl(${hue},50%,40%)`;
}

function formatPercent(v,d=4){ if(!v&&v!==0)return "-"; return (Number(v)*100).toFixed(d)+"%";}
function formatCurrency(v){ if(!v&&v!==0)return "-"; return new Intl.NumberFormat("en-US",{minimumFractionDigits:2,maximumFractionDigits:2}).format(Number(v));}
function formatDecimal(v,d=4){ if(!v&&v!==0)return "-"; return Number(v).toFixed(d);}

async function lookup(){

const address=document.getElementById("address").value.trim();
const resultsDiv=document.getElementById("results");

if(!address){
resultsDiv.innerHTML="<div class='card'>Address required.</div>";
return;
}

resultsDiv.innerHTML=`
<div class='card loading'>
<div class='spinner'></div>
Running analysis...
</div>
`;

try{
const response=await fetch("/lookup",{method:"POST",headers:{"Content-Type":"application/json"},
body:JSON.stringify({
address:address,
building_value:parseInt(document.getElementById("building_value").value) || 0,
contents_value:parseInt(document.getElementById("contents_value").value) || 0,
business_interruption_value:parseInt(document.getElementById("business_interruption_value").value) || 0
})
});

const data=await response.json();
if(!response.ok){
resultsDiv.innerHTML=`
<div class='card'>
<div class='section-title'>Input Format Error</div>
<div class='metric'>Please enter address in the following format:</div>
<div class='metric-strong'>Street, City, State ZIP</div>
<div class='metric'>Example: 1387 Schuyler Road, Beverly Hills, CA 90210</div>
</div>
`;
return;
}

const buildingValue=parseInt(document.getElementById("building_value").value)||0;
const contentsValue=parseInt(document.getElementById("contents_value").value)||0;
const biValue = parseInt(document.getElementById("business_interruption_value").value) || 0;

const overall=data.wildfire_risk.overall_score;
const mapsLink=`https://www.google.com/maps?q=${data.location.latitude},${data.location.longitude}`;

const riskYears=[
{label:"100 Year",score:data.wildfire_risk.score_100yr},
{label:"250 Year",score:data.wildfire_risk.score_250yr},
{label:"500 Year",score:data.wildfire_risk.score_500yr}
];

let riskHTML="";
riskYears.forEach(r=>{
const ratio=getDamageRatio(r.score);
const upper=ratio[1]/100;

let expectedLossDisplay="";
if(buildingValue>0){
expectedLossDisplay=formatCurrency(buildingValue*upper);
}else{
expectedLossDisplay="<span class='placeholder'>Input building value</span>";
}

riskHTML+=`
<div class="data-card">
<div class="card-title">100 Year</div>
<div class="card-sub">Risk Score: ${r.score}</div>
<div class="card-sub">Damage Ratio: ${ratio[0]}% – ${ratio[1]}%</div>
<div class="card-value">${expectedLossDisplay}</div>
</div>
`;
});

let annualBuildingLossDisplay="";
let annualContentsLossDisplay="";
let annualBusinessInterruptionLossDisplay = "";

/* Building */
if(buildingValue > 0){
    annualBuildingLossDisplay =
        formatCurrency(
            data.loss_metrics.building_annual_loss_rate * buildingValue
        );
}else{
    annualBuildingLossDisplay =
        "<span class='placeholder'>Input building value</span>";
}

/* Contents */
if(contentsValue > 0){
    annualContentsLossDisplay =
        formatCurrency(
            data.loss_metrics.contents_annual_loss_rate * contentsValue
        );
}else{
    annualContentsLossDisplay =
        "<span class='placeholder'>Input contents value</span>";
}

/* Business Interruption */
if(biValue > 0){
    annualBusinessInterruptionLossDisplay =
        formatCurrency(
            data.loss_metrics.business_interruption_annual_loss_rate * biValue
        );
}else{
    annualBusinessInterruptionLossDisplay =
        "<span class='placeholder'>Input business interruption value</span>";
}

resultsDiv.innerHTML=`

<div class="card">
<div class="section-title">
<i data-lucide="map-pin"></i>
Location
</div>
<div class="metric">Address: ${data.location.address}</div>
<div class="metric">City: ${data.location.city}</div>
<div class="metric">County: ${data.location.county}</div>
<div class="metric">State: ${data.location.state}</div>
<div class="metric">ZIP: ${data.location.postal_code}</div>
<div class="metric">Latitude: ${formatDecimal(data.location.latitude)}</div>
<div class="metric">Longitude: ${formatDecimal(data.location.longitude)}</div>
<div class="metric"><a href="${mapsLink}" target="_blank">View on Google Maps</a></div>
</div>

<div class="card">
<div class="section-title">
<i data-lucide="flame"></i>
Wildfire Risk
</div>
<div class="metric">
Overall Score:
<span class="risk-badge" style="background:${riskColor(overall)}">${overall}</span>
</div>
<div class="risk-wrapper">
<div class="risk-grid">
${riskHTML}
</div>
</div>
</div>

<div class="card">
<div class="section-title">
<i data-lucide="trending-up"></i>
Annualized Loss
</div>

<div class="loss-section">
<div class="risk-grid">

<div class="data-card">
<div class="card-title">Building AAL</div>
<div class="card-value">${annualBuildingLossDisplay}</div>
<div class="card-sub">ALR: ${formatPercent(data.loss_metrics.building_annual_loss_rate)}</div>
</div>

<div class="data-card">
<div class="card-title">Contents AAL</div>
<div class="card-value">${annualContentsLossDisplay}</div>
<div class="card-sub">ALR: ${formatPercent(data.loss_metrics.contents_annual_loss_rate)}</div>
</div>

<div class="data-card">
<div class="card-title">BI AAL</div>
<div class="card-value">${annualBusinessInterruptionLossDisplay}</div>
<div class="card-sub">ALR: ${formatPercent(data.loss_metrics.business_interruption_annual_loss_rate)}</div>
</div>

</div>

<div class="summary-section">
    <div class="summary-title">Average Annual Loss</div>
    <div class="summary-value">
        ${formatCurrency(data.loss_metrics.total_aal)}
    </div>
</div>
`;

lucide.createIcons();

}catch(err){
resultsDiv.innerHTML="<div class='card'>Request failed.</div>";
}
}

function downloadHistory() {
    window.open("/download-history", "_blank");
}

</script>

</body>
</html>
"""

# =========================
# API Endpoint
# =========================
@app.post("/lookup")
def lookup(req: LookupRequest):

    street, city, state, zip_code = parse_address(req.address)
    normalized_address = normalize_address(street, city, state, zip_code)
    cached = get_location_cache_by_address(normalized_address)

    if cached:
        print("FULL CACHE HIT - NO RMS API CALLED")

        geo_res = {
            "streetAddress": cached.Street,
            "cityName": cached.City,
            "admin2Name": cached.County,
            "admin1Code": cached.State,
            "postalCode": cached.ZipCode,
            "latitude": cached.Latitude,
            "longitude": cached.Longitude
        }

        risk_res = {
            "scoreOverall": cached.OverallScore,
            "score100yr": cached.Score100yr,
            "score250yr": cached.Score250yr,
            "score500yr": cached.Score500yr
        }

        loss_res = {
            "buildingAlr": cached.BuildingALR,
            "contentsAlr": cached.ContentsALR,
            "businessInterruptionAlr": cached.BusinessInterruptionALR
        }

        lat = cached.Latitude
        lon = cached.Longitude

    else:
        print("CACHE MISS - CALLING RMS ONCE (geocode+risk+loss)")

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
                    "construction": "ATC1"
                },
                "coverageValues": {
                    "buildingValue": req.building_value or 0,
                    "contentsValue": req.contents_value or 0,
                    "businessInterruptionValue": req.business_interruption_value or 0
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
            raise HTTPException(status_code=response.status_code, detail=response.text)

        data = response.json()

        geocode_layer = next((x for x in data if x["name"] == "geocode"), {})
        risk_layer = next((x for x in data if x["name"] == "us_wf_risk_score"), {})
        loss_layer = next((x for x in data if x["name"] == "us_wf_loss_cost"), {})

        geo_res = geocode_layer.get("results", {})
        risk_res = risk_layer.get("results", {})
        loss_res = loss_layer.get("results", {})

        lat = geo_res.get("latitude")
        lon = geo_res.get("longitude")
        if lat is None or lon is None:
            raise HTTPException(status_code=400, detail="Geocoding failed")

        lat = round(float(lat), 6)
        lon = round(float(lon), 6)

        insert_location_cache(
            lat,
            lon,
            geo_res,
            risk_res,
            loss_res,
            json.dumps(data),
            normalized_address
        )

        cached = get_location_cache_by_address(normalized_address)

        print("INSERTED INTO CACHE")

    location_id = cached.LocationRiskId

    building_value = float(req.building_value or 0)
    contents_value = float(req.contents_value or 0)
    bi_value = float(req.business_interruption_value or 0)

    building_alr = float(loss_res.get("buildingAlr") or 0)
    contents_alr = float(loss_res.get("contentsAlr") or 0)
    bi_alr = float(loss_res.get("businessInterruptionAlr") or 0)

    building_aal = building_alr * building_value
    contents_aal = contents_alr * contents_value
    bi_aal = bi_alr * bi_value

    total_aal = building_aal + contents_aal + bi_aal

    if not query_history_exists(location_id, req):
        insert_query_history(
            location_id,
            req,
            loss_res.get("buildingAlr"),
            loss_res.get("contentsAlr"),
            loss_res.get("businessInterruptionAlr")
        )
        print("QUERY HISTORY INSERTED")
    else:
        print("DUPLICATE QUERY - NOT INSERTED")

    result = {
        "location": {
            "address": geo_res.get("streetAddress"),
            "city": geo_res.get("cityName"),
            "county": geo_res.get("admin2Name"),
            "state": geo_res.get("admin1Code"),
            "postal_code": geo_res.get("postalCode"),
            "latitude": geo_res.get("latitude"),
            "longitude": geo_res.get("longitude")
        },
        "wildfire_risk": {
            "overall_score": risk_res.get("scoreOverall"),
            "score_100yr": risk_res.get("score100yr"),
            "score_250yr": risk_res.get("score250yr"),
            "score_500yr": risk_res.get("score500yr")
        },
        "loss_metrics": {
            "building_annual_loss_rate": building_alr,
            "contents_annual_loss_rate": contents_alr,
            "business_interruption_annual_loss_rate": bi_alr,
            "building_aal": building_aal,
            "contents_aal": contents_aal,
            "bi_aal": bi_aal,
            "total_aal": total_aal
        }
    }

    return result

@app.get("/download-history")
def download_history():
    try:
        conn = get_mssql_conn()

        query = """
        SELECT
            l.Street,
            l.City,
            l.County,
            l.State,
            l.ZipCode,
            l.Latitude,
            l.Longitude,
            q.BuildingValue,
            q.ContentsValue,
            q.BusinessInterruptionValue,
            l.OverallScore,
            l.Score100yr,
            l.Score250yr,
            l.Score500yr,
            l.BuildingALR,
            l.ContentsALR,
            l.BusinessInterruptionALR,
            q.BuildingAAL,
            q.ContentsAAL,
            q.BusinessInterruptionAAL,
            q.TotalAAL
        FROM dbo.Moodys_Query_History q
        INNER JOIN dbo.Moodys_Location_Risk l
            ON q.LocationRiskId = l.LocationRiskId
        ORDER BY q.QueriedAt DESC;
        """

        df = pd.read_sql(query, conn)
        conn.close()

        output = io.BytesIO()
        with pd.ExcelWriter(output, engine="openpyxl") as writer:
            df.to_excel(writer, index=False, sheet_name="Location Risk")


        output.seek(0)

        filename = f"Moodys_Risk_Export_{datetime.now().strftime('%Y%m%d')}.xlsx"

        return StreamingResponse(
            output,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={
                "Content-Disposition": f"attachment; filename={filename}"
            },
        )

    except Exception as e:
        return {"error": str(e)}
    
if __name__ == "__main__":
    import uvicorn
    import webbrowser
    import threading

    def open_browser():
        webbrowser.open("http://127.0.0.1:8000")

    threading.Timer(1.5, open_browser).start()

    uvicorn.run(
        app,
        host="127.0.0.1",
        port=8000,
        log_config=None
    )
