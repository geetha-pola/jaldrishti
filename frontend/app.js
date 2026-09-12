const API_BASE_URL = 'http://localhost:8000/api/v1';

const titles={dashboard:'Flood Inundation Dashboard','glof-select':'GLOF — Select Lake','glof-character':'GLOF — Lake Characterization','glof-trigger':'GLOF — Trigger Assessment','glof-scenario':'GLOF — Outburst Scenario','dam-select':'Dam Break — Select Dam','dam-condition':'Dam Break — Reservoir Condition','dam-breach':'Dam Break — Breach Scenario',data:'Data Acquisition',preprocess:'Automatic Data Preprocessing',domain:'Simulation Domain',scenario:'Scenario Generator',model:'Hydrodynamic Model Adapter',simulation:'Simulation Progress',results:'Flood Inundation Results',propagation:'Flood Propagation Timeline',compare:'Scenario Comparison',impact:'Flood Impact Analysis',validation:'Satellite-Based Validation',export:'Export Results',history:'Simulation History',architecture:'JALDRISHTI System Architecture',stack:'Technology Stack',about:'About JALDRISHTI'};

function go(id){
    document.querySelectorAll('.page').forEach(p=>p.classList.remove('active'));
    const el=document.getElementById(id);
    if(el)el.classList.add('active');
    document.querySelectorAll('.nav').forEach(n=>n.classList.toggle('active',n.dataset.page===id));
    document.getElementById('title').textContent=titles[id]||'JALDRISHTI';
    window.scrollTo(0,0);
}

document.querySelectorAll('.nav').forEach(n=>n.onclick=()=>go(n.dataset.page));

// Mock SVG maps for visual steps
function mockMap(id){
  const el=document.getElementById(id);
  if(!el || el.dataset.mapReady==="1")return;
  el.dataset.mapReady="1";
  el.classList.add("offline-map");
  el.innerHTML=`
    <div class="offline-map-bg">
      <div class="map-grid"></div>
      <svg viewBox="0 0 900 500" preserveAspectRatio="none">
        <path class="terrain t1" d="M0 70 L130 20 L260 90 L390 35 L520 100 L650 45 L790 110 L900 60 L900 0 L0 0Z"/>
        <path class="terrain t2" d="M0 420 L120 350 L250 410 L370 330 L510 405 L650 340 L780 410 L900 350 L900 500 L0 500Z"/>
        <circle class="marker-ring" cx="450" cy="255" r="15"/>
        <circle class="marker" cx="450" cy="255" r="7"/>
      </svg>
      <div class="map-title">OFFLINE DEMO MAP</div>
    </div>`;
}
mockMap('mapG'); mockMap('mapD'); mockMap('mapDomain'); mockMap('mapProp'); mockMap('mapVal1'); mockMap('mapVal2'); mockMap('mapImpact');

function toast(msg){const t=document.getElementById('toast');t.textContent=msg;t.style.display='block';setTimeout(()=>t.style.display='none',1800)}

// Application State
let availableDams = [];
let selectedDamId = null;
let currentSimulationId = null;

async function loadDams() {
    try {
        const response = await fetch(`${API_BASE_URL}/dams`);
        availableDams = await response.json();
        
        const select = document.getElementById('api-dam-select');
        select.innerHTML = '<option value="">-- Choose a Dam --</option>';
        availableDams.forEach(dam => {
            select.innerHTML += `<option value="${dam.id}">${dam.name} (${dam.state})</option>`;
        });
    } catch (e) {
        console.error("Failed to load dams", e);
        document.getElementById('api-dam-select').innerHTML = '<option value="">Error loading dams</option>';
    }
}

window.selectDam = function(id) {
    selectedDamId = id;
    const btn = document.getElementById('btn-dam-continue');
    const info = document.getElementById('selected-dam-info');
    
    if (!id) {
        btn.disabled = true;
        info.innerHTML = "<b>Selected: None</b>";
        return;
    }
    
    const dam = availableDams.find(d => d.id == id);
    if(dam) {
        btn.disabled = false;
        info.innerHTML = `<b>Selected: ${dam.name}</b><span>${dam.river || 'Unknown River'} • ${dam.state}</span>`;
        
        // Update condition page
        document.getElementById('cond-level').textContent = "Unknown";
        document.getElementById('cond-storage').textContent = dam.latest_storage_mcm ? `${dam.latest_storage_mcm} Mm³` : "Unknown";
        document.getElementById('cond-cap').textContent = dam.capacity_mcm ? `${dam.capacity_mcm} Mm³` : "Unknown";
        document.getElementById('cond-height').textContent = dam.height_m ? `${dam.height_m} m` : "Unknown";
        document.getElementById('cond-date').textContent = "Hypothetical Scenario";
    }
};

window.startSimulation = async function() {
    if (!selectedDamId) return;
    
    go('simulation');
    
    document.getElementById('sim-status-badge').textContent = 'Processing';
    document.getElementById('sim-current-stage').textContent = 'Initializing';
    document.getElementById('sim-progress-text').textContent = '0%';
    document.getElementById('sim-progress-bar').style.width = '0%';
    document.getElementById('btn-open-results').disabled = true;
    document.getElementById('sim-error-text').textContent = '';
    
    try {
        const response = await fetch(`${API_BASE_URL}/simulations`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                hazard_type: "DAM_BREAK",
                dam_id: selectedDamId.toString()
            })
        });
        
        const data = await response.json();
        currentSimulationId = data.simulation_id;
        document.getElementById('sim-id-text').textContent = currentSimulationId;
        
        pollSimulation(currentSimulationId);
    } catch (e) {
        document.getElementById('sim-status-badge').textContent = 'Failed';
        document.getElementById('sim-error-text').textContent = e.message;
    }
};

async function pollSimulation(simId) {
    try {
        const response = await fetch(`${API_BASE_URL}/simulations/${simId}`);
        const data = await response.json();
        
        document.getElementById('sim-current-stage').textContent = data.current_stage || data.status;
        const progress = data.progress || 0;
        document.getElementById('sim-progress-text').textContent = `${progress}%`;
        document.getElementById('sim-progress-bar').style.width = `${progress}%`;
        
        if (data.status === 'COMPLETED') {
            document.getElementById('sim-status-badge').textContent = 'Completed';
            document.getElementById('sim-status-badge').className = 'status detected';
            document.getElementById('btn-open-results').disabled = false;
            fetchResults(simId);
        } else if (data.status === 'FAILED') {
            document.getElementById('sim-status-badge').textContent = 'Failed';
            document.getElementById('sim-status-badge').className = 'status unknown';
            document.getElementById('sim-error-text').textContent = data.error;
        } else {
            setTimeout(() => pollSimulation(simId), 1000);
        }
    } catch (e) {
        console.error(e);
        setTimeout(() => pollSimulation(simId), 2000);
    }
}

async function fetchResults(simId) {
    try {
        // Fetch basic results first
        const resultsResp = await fetch(`${API_BASE_URL}/simulations/${simId}/results`);
        if (resultsResp.ok) {
            const resultsData = await resultsResp.json();
            if (resultsData.max_depth_m) {
                document.getElementById('res-depth').textContent = `${resultsData.max_depth_m.toFixed(2)} m`;
            }
            if (resultsData.max_velocity_mps) {
                document.getElementById('res-vel').textContent = `${resultsData.max_velocity_mps.toFixed(2)} m/s`;
            }
        }
        
        // Impact Analysis
        const impactResp = await fetch(`${API_BASE_URL}/simulations/${simId}/impact`);
        if (impactResp.ok) {
            const impactData = await impactResp.json();
            document.getElementById('res-area').textContent = `${impactData.flooded_area_km2.toFixed(2)} km²`;
            document.getElementById('res-arrival').textContent = "Model-estimated flood arrival";
            
            const places = impactData.places;
            document.getElementById('impact-places-count').textContent = places.length;
            
            let listHtml = "<b>Nearest Affected Places</b><br>";
            places.forEach(p => {
                listHtml += `<div style="display:flex;justify-content:space-between;border-bottom:1px solid #eee;padding:4px 0;">
                    <span>${p.name} (${p.type})</span>
                    <b>→ ${Math.round(p.flood_arrival_minutes)} min</b>
                </div>`;
            });
            document.getElementById('impact-places-list').innerHTML = listHtml;
        }

        // Satellite Validation
        const satResp = await fetch(`${API_BASE_URL}/simulations/${simId}/satellite`);
        if (satResp.ok) {
            const satData = await satResp.json();
            document.getElementById('sat-modelled-area').textContent = `${satData.modeled_area_km2.toFixed(2)} km²`;
            document.getElementById('sat-observed-area').textContent = `${satData.observed_area_km2.toFixed(2)} km²`;
            document.getElementById('sat-iou').textContent = `${satData.iou.toFixed(2)}%`;
            document.getElementById('sat-obs-area2').textContent = `${satData.observed_area_km2.toFixed(2)} km²`;
            document.getElementById('sat-status').textContent = satData.validation_status;
            
            if (satData.limitations) {
                document.getElementById('sat-limitations').innerHTML = satData.limitations.map(l => `• ${l}`).join("<br>");
            }
        }
        
        // GeoJSON Map
        initLeafletMap(simId);
        
    } catch (e) {
        console.error("Failed fetching results", e);
    }
}

function initLeafletMap(simId) {
    const el = document.getElementById('mapResult');
    if (!el || el.dataset.leafletReady === "1") return;
    el.dataset.leafletReady = "1";
    el.innerHTML = ""; // clear mock
    
    const map = L.map('mapResult').setView([9.84, 76.97], 11);
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
        attribution: '© OpenStreetMap'
    }).addTo(map);
    
    fetch(`${API_BASE_URL}/simulations/${simId}/geojson`)
        .then(r => r.json())
        .then(data => {
            const layer = L.geoJSON(data, {
                style: function (feature) {
                    return {color: "#0066cc", weight: 1, fillOpacity: 0.5};
                }
            }).addTo(map);
            map.fitBounds(layer.getBounds());
        })
        .catch(e => console.error("GeoJSON error:", e));
}

// Init
window.addEventListener('DOMContentLoaded', loadDams);