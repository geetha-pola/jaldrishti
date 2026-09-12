with open('frontend/app.js', 'r') as f:
    content = f.read()

lake_logic = """
let currentLakes = [];
let selectedLakeId = null;
let currentHazard = 'DAM_BREAK';

async function getLakes() {
    try {
        const response = await fetch(API_BASE_URL + '/lakes');
        if (response.ok) {
            currentLakes = await response.json();
            const select = document.getElementById('api-lake-select');
            if (select) {
                select.innerHTML = '<option value="">-- Select a lake --</option>';
                currentLakes.forEach(l => {
                    const opt = document.createElement('option');
                    opt.value = l.id;
                    opt.textContent = l.name;
                    select.appendChild(opt);
                });
            }
        }
    } catch(e) { console.error('Failed to load lakes', e); }
}

window.selectLake = function(id) {
    selectedLakeId = id;
    const info = document.getElementById('selected-lake-info');
    const btn = document.getElementById('btn-glof-char');
    
    if (!id) {
        info.innerHTML = '<b>Selected: None</b>';
        btn.disabled = true;
        return;
    }
    const lake = currentLakes.find(l => l.id === id);
    if (lake) {
        currentHazard = 'GLOF';
        info.innerHTML = '<b>Selected: ' + lake.name + '</b><span>' + lake.latitude + 'N, ' + lake.longitude + 'E &bull; ' + lake.elevation_m + 'm</span>';
        btn.disabled = false;
        
        // Populate characterization
        document.getElementById('lake-area').textContent = (lake.area_sq_m / 1000000).toFixed(2) + ' km2';
        document.getElementById('lake-elev').textContent = lake.elevation_m + ' m';
        document.getElementById('lake-vol').textContent = (lake.estimated_volume_m3 / 1000000).toFixed(2) + ' Mm3';
        document.getElementById('lake-depth').textContent = lake.estimated_depth_m + ' m';
        document.getElementById('lake-river').textContent = lake.downstream_river || '-';
        document.getElementById('lake-prov').textContent = lake.provenance;
    }
}
"""

content += '\n' + lake_logic + '\ngetLakes();\n'

# Update startDynamicSimulation
content = content.replace("hazard_type: 'DAM_BREAK',", "hazard_type: currentHazard,")
content = content.replace("dam_id: damId,", "dam_id: currentHazard === 'DAM_BREAK' ? damId : undefined,\n                lake_id: currentHazard === 'GLOF' ? selectedLakeId : undefined,")

with open('frontend/app.js', 'w') as f:
    f.write(content)
