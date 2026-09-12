const titles={dashboard:'Flood Inundation Dashboard','glof-select':'GLOF — Select Lake','glof-character':'GLOF — Lake Characterization','glof-trigger':'GLOF — Trigger Assessment','glof-scenario':'GLOF — Outburst Scenario','dam-select':'Dam Break — Select Dam','dam-condition':'Dam Break — Reservoir Condition','dam-breach':'Dam Break — Breach Scenario',data:'Data Acquisition',preprocess:'Automatic Data Preprocessing',domain:'Simulation Domain',scenario:'Scenario Generator',model:'Hydrodynamic Model Adapter',simulation:'Simulation Progress',results:'Flood Inundation Results',propagation:'Flood Propagation Timeline',compare:'Scenario Comparison',impact:'Flood Impact Analysis',validation:'Satellite-Based Validation',export:'Export Results',history:'Simulation History',architecture:'JALDRISHTI System Architecture',stack:'Technology Stack',about:'About JALDRISHTI'};
function go(id){document.querySelectorAll('.page').forEach(p=>p.classList.remove('active'));const el=document.getElementById(id);if(el)el.classList.add('active');document.querySelectorAll('.nav').forEach(n=>n.classList.toggle('active',n.dataset.page===id));document.getElementById('title').textContent=titles[id]||'JALDRISHTI';setTimeout(initMaps,50);window.scrollTo(0,0)}
document.querySelectorAll('.nav').forEach(n=>n.onclick=()=>go(n.dataset.page));
let maps={};

function map(id,lat=30.3,lon=79.4,zoom=9){
  const el=document.getElementById(id);
  if(!el)return;
  if(el.dataset.mapReady==="1")return;
  el.dataset.mapReady="1";

  el.classList.add("offline-map");
  el.innerHTML=`
    <div class="offline-map-bg">
      <div class="map-grid"></div>
      <svg viewBox="0 0 900 500" preserveAspectRatio="none" aria-label="JALDRISHTI study area map">
        <path class="terrain t1" d="M0 70 L130 20 L260 90 L390 35 L520 100 L650 45 L790 110 L900 60 L900 0 L0 0Z"/>
        <path class="terrain t2" d="M0 420 L120 350 L250 410 L370 330 L510 405 L650 340 L780 410 L900 350 L900 500 L0 500Z"/>
        <path class="road" d="M-20 430 C150 390 260 400 380 330 S650 250 920 120"/>
        <path class="road secondary" d="M30 100 C180 160 270 210 400 185 S690 140 920 190"/>
        <path class="river" d="M120 -20 C210 80 150 145 270 205 S330 330 440 370 S650 390 720 520"/>
        <path class="river2" d="M705 -20 C650 70 690 150 610 230 S550 330 600 500"/>
        <path class="flood" d="M285 170 C350 145 420 160 470 210 C515 255 485 320 535 350 C570 372 585 410 545 438 C475 458 420 415 380 395 C335 370 300 325 320 285 C340 245 275 220 285 170Z"/>
        <path class="domain" d="M250 115 L570 105 L710 250 L620 440 L330 430 L205 280Z"/>
        <circle class="marker-ring" cx="450" cy="255" r="15"/>
        <circle class="marker" cx="450" cy="255" r="7"/>
        <text x="462" y="250" class="label">Selected study location</text>
        <text x="55" y="455" class="place">Downstream valley</text>
        <text x="700" y="105" class="place">Terrain / ridge</text>
        <text x="510" y="300" class="water-label">Flood extent</text>
      </svg>
      <div class="map-title">OFFLINE DEMO MAP • ${lat.toFixed(2)}°, ${lon.toFixed(2)}°</div>
      <div class="map-legend">
        <span><i class="legend-flood"></i> Simulated flood</span>
        <span><i class="legend-river"></i> River / drainage</span>
        <span><i class="legend-road"></i> Road</span>
      </div>
      <div class="map-controls"><button onclick="this.parentElement.parentElement.querySelector('svg').style.transform='scale(1.08)'">+</button><button onclick="this.parentElement.parentElement.querySelector('svg').style.transform='scale(1)'">−</button></div>
    </div>`;
  maps[id]={invalidateSize:()=>{}};
}

function initMaps(){
  map('mapG');
  map('mapD',30.2,79.5);
  map('mapDomain',30.2,79.5);
  map('mapResult');
  map('mapProp');
  map('mapImpact');
  map('mapVal1');
  map('mapVal2',30.31,79.46);
}

const slider=document.getElementById('timeSlider');
const timeValue=document.getElementById('timeValue');

function updatePropagation(){
  if(!slider) return;
  const t=Number(slider.value);
  if(timeValue) timeValue.textContent=t+" min";

  // Visually change the simulated flood footprint as time increases.
  const mapEl=document.getElementById('mapProp');
  if(!mapEl) return;
  const flood=mapEl.querySelector('.flood');
  const label=mapEl.querySelector('.water-label');
  if(!flood) return;

  const p=Math.max(0,Math.min(1,t/37));
  const scale=0.45 + p*0.65;
  flood.style.transformOrigin="450px 300px";
  flood.style.transform=`scale(${scale.toFixed(2)})`;

  if(label) label.textContent=`Flood extent • ${t} min`;

  // Update the small metric cards below the map when they exist.
  const cards=mapEl.parentElement?.parentElement?.querySelectorAll?.('.metric-value') || [];
  if(cards.length){
    if(cards[0]) cards[0].textContent=(18.5 + p*24.3).toFixed(1)+" km²";
    if(cards[1]) cards[1].textContent=(1.8 + p*6.6).toFixed(1)+" m";
    if(cards[2]) cards[2].textContent=(1.6 + p*4.6).toFixed(1)+" m/s";
  }
}

if(slider){
  slider.addEventListener('input',updatePropagation);
  slider.addEventListener('change',updatePropagation);
}

function toast(msg){const t=document.getElementById('toast');t.textContent=msg;t.style.display='block';setTimeout(()=>t.style.display='none',1800)}
initMaps();