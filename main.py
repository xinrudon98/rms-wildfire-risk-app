import os
import requests
from typing import Optional
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
import psycopg2
from datetime import datetime

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
    conn = psycopg2.connect(os.getenv("DATABASE_URL"))
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS risk_queries (
            id SERIAL PRIMARY KEY,
            timestamp TIMESTAMP,
            address TEXT,
            city TEXT,
            state TEXT,
            county TEXT,
            overall_score INT,
            score_100 INT,
            score_250 INT,
            score_500 INT,
            building_value FLOAT,
            contents_value FLOAT,
            business_interruption_value FLOAT,
            expected_loss FLOAT,
            annual_building_loss FLOAT,
            annual_contents_loss FLOAT,
            annual_bi_loss FLOAT,
            average_annual_loss FLOAT
        );
    """)

    conn.commit()
    cur.close()
    conn.close()

init_db()

# =========================
# Request Model
# =========================
class LookupRequest(BaseModel):
    address: str
    year_built: Optional[int] = 0
    num_stories: Optional[int] = 0
    sqft: Optional[int] = 0
    building_value: Optional[float] = 0
    contents_value: Optional[float] = 0
    business_interruption_value: Optional[float] = 0

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

.risk-card{
background:white;
padding:22px;
border-radius:12px;
border-left:4px solid #8497B0;
transition:all 0.2s ease;
}

.risk-card:hover{
transform:translateY(-2px);
box-shadow:0 8px 20px rgba(0,0,0,0.05);
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
grid-template-columns:1fr 1fr;
gap:30px;
}

.loss-card{
background:white;
padding:22px;
border-radius:12px;
border-top:4px solid #EEE1B3;
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
<h1>RMS WILDFIRE RISK LOOKUP</h1>
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
<input id="year_built" type="number" placeholder="Year Built"/>
<input id="num_stories" type="number" placeholder="Number of Stories"/>
<input id="sqft" type="number" placeholder="Square Footage"/>
<input id="building_value" type="number" placeholder="Building Value"/>
<input id="contents_value" type="number" placeholder="Contents Value"/>
<input id="business_interruption_value" type="number" placeholder="Business Interruption Value"/>
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
10:[50,80]
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
year_built:parseInt(document.getElementById("year_built").value)||0,
num_stories:parseInt(document.getElementById("num_stories").value)||0,
sqft:parseInt(document.getElementById("sqft").value)||0,
building_value:parseFloat(document.getElementById("building_value").value)||0,
contents_value:parseFloat(document.getElementById("contents_value").value)||0,
business_interruption_value:parseFloat(document.getElementById("business_interruption_value").value)||0
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

const buildingValue=parseFloat(document.getElementById("building_value").value)||0;
const contentsValue=parseFloat(document.getElementById("contents_value").value)||0;
const biValue = parseFloat(document.getElementById("business_interruption_value").value) || 0;

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
<div class="risk-card">
<div class="risk-title">${r.label}</div>
<div class="metric">Risk Score: ${r.score}</div>
<div class="metric">Estimated Damage Ratio: ${ratio[0]}% – ${ratio[1]}%</div>
<div class="metric">Expected Loss</div>
<div class="metric-strong">${expectedLossDisplay}</div>
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
<div class="loss-grid">

<div class="loss-card">
<div class="metric">Building Annualized Loss Rate</div>
<div class="metric">${formatPercent(data.loss_metrics.building_annual_loss_rate)}</div>
<div class="metric">Estimated Annual Building Loss</div>
<div class="metric">${annualBuildingLossDisplay}</div>
</div>

<div class="loss-card">
<div class="metric">Contents Annualized Loss Rate</div>
<div class="metric">${formatPercent(data.loss_metrics.contents_annual_loss_rate)}</div>
<div class="metric">Estimated Annual Contents Loss</div>
<div class="metric">${annualContentsLossDisplay}</div>
</div>

<div class="loss-card">
<div class="metric">Business Interruption Annualized Loss Rate</div>
<div class="metric">${formatPercent(data.loss_metrics.business_interruption_annual_loss_rate)}</div>
<div class="metric">Estimated Annual Business Interruption Loss</div>
<div class="metric">${annualBusinessInterruptionLossDisplay}</div>
</div>

</div>

<div style="margin-top:30px;">
<div class="metric">Average Annual Loss</div>
<div class="metric-strong">
${formatCurrency(data.loss_metrics.ground_up_loss)}
</div>
</div>

</div>
</div>
`;

lucide.createIcons();

}catch(err){
resultsDiv.innerHTML="<div class='card'>Request failed.</div>";
}
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
                "construction": "ATC1",
                "occupancy": "ATC1",
                "yearBuilt": req.year_built or 0,
                "numOfStories": req.num_stories or 0,
                "foundationType": 0,
                "floorArea": req.sqft or 0
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
        raise HTTPException(
            status_code=response.status_code,
            detail=response.text
        )

    data = response.json()

    geocode = next((x for x in data if x["name"] == "geocode"), {})
    risk = next((x for x in data if x["name"] == "us_wf_risk_score"), {})
    loss = next((x for x in data if x["name"] == "us_wf_loss_cost"), {})

    geo_res = geocode.get("results", {})
    risk_res = risk.get("results", {})
    loss_res = loss.get("results", {})

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
            "building_annual_loss_rate": loss_res.get("buildingAlr"),
            "contents_annual_loss_rate": loss_res.get("contentsAlr"),
            "business_interruption_annual_loss_rate": loss_res.get("businessInterruptionAlr"),
            "ground_up_loss": loss_res.get("groundUpLoss")
        }
    }

    # =========================
    # Save Query to Database
    # =========================
    try:
        db_url = os.getenv("DATABASE_URL")
        if not db_url:
            print("DATABASE_URL not set")
            return result

        conn = psycopg2.connect(db_url)
        cur = conn.cursor()

        overall_score = risk_res.get("scoreOverall")
        score_100 = risk_res.get("score100yr")
        score_250 = risk_res.get("score250yr")
        score_500 = risk_res.get("score500yr")

        city = geo_res.get("cityName")
        state = geo_res.get("admin1Code")
        county = geo_res.get("admin2Name")

        building_value = req.building_value or 0
        contents_value = req.contents_value or 0
        bi_value = req.business_interruption_value or 0

        ratio_map = {
            1:(0,0.5),2:(0.5,1),3:(1,5),4:(5,10),
            5:(10,15),6:(15,20),7:(20,30),
            8:(30,40),9:(40,50),10:(50,80)
        }

        upper_ratio = ratio_map.get(score_100, (0,0))[1] / 100
        expected_loss = building_value * upper_ratio

        building_alr = loss_res.get("buildingAlr") or 0
        contents_alr = loss_res.get("contentsAlr") or 0
        bi_alr = loss_res.get("businessInterruptionAlr") or 0

        annual_building_loss = building_alr * building_value
        annual_contents_loss = contents_alr * contents_value
        annual_bi_loss = bi_alr * bi_value

        average_annual_loss = loss_res.get("groundUpLoss") or 0

        cur.execute("""
            INSERT INTO risk_queries (
                timestamp,
                address,
                city,
                state,
                county,
                overall_score,
                score_100,
                score_250,
                score_500,
                building_value,
                contents_value,
                business_interruption_value,
                expected_loss,
                annual_building_loss,
                annual_contents_loss,
                annual_bi_loss,
                average_annual_loss
            )
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        """, (
            datetime.now(),
            req.address,
            city,
            state,
            county,
            overall_score,
            score_100,
            score_250,
            score_500,
            building_value,
            contents_value,
            bi_value,
            expected_loss,
            annual_building_loss,
            annual_contents_loss,
            annual_bi_loss,
            average_annual_loss
        ))

        conn.commit()
        cur.close()
        conn.close()

    except Exception as e:
        print("Database write error:", e)

    return result
