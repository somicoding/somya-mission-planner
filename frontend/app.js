/**
 * AERO-GCS Ground Control Station Live Telemetry Engine
 */

// State
let ws = null;
let currentDroneId = "";
let isConnected = false;
let isPaused = false;
let packetCount = 0;
let lastPacketTime = Date.now();
let packetsThisSecond = 0;
let flightStartTime = Date.now();

// Smooth Attitude State (Interpolated for 60fps render)
const targetAttitude = { roll: 0, pitch: 0, yaw: 0 };
const currentAttitude = { roll: 0, pitch: 0, yaw: 0 };

// Map Elements
let map = null;
let droneMarker = null;
let flightPathPolyline = null;
const flightCoordinates = [];

// DOM Elements
const systemStatusPill = document.getElementById("systemStatusPill");
const connectionStatusText = document.getElementById("connectionStatusText");
const droneSelector = document.getElementById("droneSelector");
const flightModeBadge = document.getElementById("flightModeBadge");
const armedBadge = document.getElementById("armedBadge");
const landedBadge = document.getElementById("landedBadge");
const streamRateVal = document.getElementById("streamRateVal");
const packetCountVal = document.getElementById("packetCountVal");
const flightTimerVal = document.getElementById("flightTimerVal");
const attitudeAngleText = document.getElementById("attitudeAngleText");
const pfdAirspeedVal = document.getElementById("pfdAirspeedVal");
const pfdAltitudeVal = document.getElementById("pfdAltitudeVal");
const headingVal = document.getElementById("headingVal");
const groundspeedVal = document.getElementById("groundspeedVal");
const groundspeedBar = document.getElementById("groundspeedBar");
const relativeAltVal = document.getElementById("relativeAltVal");
const altitudeBar = document.getElementById("altitudeBar");
const climbVal = document.getElementById("climbVal");
const climbBar = document.getElementById("climbBar");
const throttleVal = document.getElementById("throttleVal");
const throttleBar = document.getElementById("throttleBar");
const coordPill = document.getElementById("coordPill");
const batteryPctBadge = document.getElementById("batteryPctBadge");
const batteryLevelBar = document.getElementById("batteryLevelBar");
const voltageVal = document.getElementById("voltageVal");
const currentVal = document.getElementById("currentVal");
const batteryTempVal = document.getElementById("batteryTempVal");
const cellVoltagesGrid = document.getElementById("cellVoltagesGrid");
const gpsFixBadge = document.getElementById("gpsFixBadge");
const satsVal = document.getElementById("satsVal");
const hdopVal = document.getElementById("hdopVal");
const rssiVal = document.getElementById("rssiVal");
const rssiBar = document.getElementById("rssiBar");
const packetTerminal = document.getElementById("packetTerminal");
const pauseLogBtn = document.getElementById("pauseLogBtn");
const horizonCanvas = document.getElementById("horizonCanvas");
const centerDroneBtn = document.getElementById("centerDroneBtn");
const clearPathBtn = document.getElementById("clearPathBtn");
const historyModalBtn = document.getElementById("historyModalBtn");
const statsModal = document.getElementById("statsModal");
const closeModalBtn = document.getElementById("closeModalBtn");
const fetchHistoryBtn = document.getElementById("fetchHistoryBtn");
const historyTable = document.getElementById("historyTable").querySelector("tbody");

// Determine Backend Host & Protocol
const loc = window.location;
const wsProtocol = loc.protocol === "https:" ? "wss:" : "ws:";
const defaultWsUrl = `${wsProtocol}//${loc.hostname || "127.0.0.1"}:${loc.port || "8000"}/api/v1/telemetry/ws/live`;
const apiBaseUrl = `${loc.protocol}//${loc.hostname || "127.0.0.1"}:${loc.port || "8000"}/api/v1`;

// ==============================================================================
// Initialization
// ==============================================================================
document.addEventListener("DOMContentLoaded", () => {
    initMap();
    initAttitudeDisplay();
    initUptimeTimer();
    initEventHandlers();
    loadDronesList().then(() => {
        connectWebSocket();
    });
});

// ==============================================================================
// Tactical Map Initialization (Leaflet)
// ==============================================================================
function initMap() {
    const defaultCoords = [37.7749, -122.4194]; // Default San Francisco
    map = L.map("droneMap", {
        zoomControl: false,
        attributionControl: false
    }).setView(defaultCoords, 16);

    L.control.zoom({ position: "bottomright" }).addTo(map);

    // Dark Tactical CartoDB Tiles
    L.tileLayer("https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png", {
        maxZoom: 20,
        subdomains: "abcd"
    }).addTo(map);

    // Custom Aircraft Heading Marker
    const droneSvgIcon = L.divIcon({
        className: "drone-map-icon",
        html: `
            <svg class="drone-svg" width="34" height="34" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                <path d="M12 2L19 21L12 17L5 21L12 2Z" fill="#00f2fe" stroke="#ffffff" stroke-width="1.5" stroke-linejoin="round"/>
            </svg>
        `,
        iconSize: [34, 34],
        iconAnchor: [17, 17]
    });

    droneMarker = L.marker(defaultCoords, { icon: droneSvgIcon }).addTo(map);

    // Flight Path Breadcrumb
    flightPathPolyline = L.polyline([], {
        color: "#00f2fe",
        weight: 3,
        opacity: 0.8,
        smoothFactor: 1
    }).addTo(map);
}

function updateDroneMapPosition(lat, lon, heading) {
    if (!lat || !lon || isNaN(lat) || isNaN(lon)) return;

    const newPos = [lat, lon];
    droneMarker.setLatLng(newPos);

    // Rotate SVG to vehicle heading
    const iconEl = droneMarker.getElement();
    if (iconEl) {
        const svg = iconEl.querySelector(".drone-svg");
        if (svg) {
            svg.style.transform = `rotate(${heading || 0}deg)`;
        }
    }

    flightCoordinates.push(newPos);
    flightPathPolyline.setLatLngs(flightCoordinates);

    coordPill.innerText = `LAT: ${lat.toFixed(6)} | LON: ${lon.toFixed(6)}`;
}

// ==============================================================================
// Artificial Horizon (PFD) 60 FPS Render
// ==============================================================================
function initAttitudeDisplay() {
    const ctx = horizonCanvas.getContext("2d");

    function renderHorizon() {
        const width = horizonCanvas.width;
        const height = horizonCanvas.height;
        const cx = width / 2;
        const cy = height / 2;

        // Smooth Lerp (Linear Interpolation)
        currentAttitude.roll += (targetAttitude.roll - currentAttitude.roll) * 0.15;
        currentAttitude.pitch += (targetAttitude.pitch - currentAttitude.pitch) * 0.15;
        currentAttitude.yaw += (targetAttitude.yaw - currentAttitude.yaw) * 0.15;

        const rollRad = (currentAttitude.roll * Math.PI) / 180;
        const pitchPixels = currentAttitude.pitch * 3.5; // 3.5px per pitch degree

        ctx.save();
        ctx.clearRect(0, 0, width, height);

        // Clip to canvas area
        ctx.beginPath();
        ctx.rect(0, 0, width, height);
        ctx.clip();

        // Translate and rotate around center
        ctx.translate(cx, cy);
        ctx.rotate(-rollRad);
        ctx.translate(0, pitchPixels);

        // Draw Sky (Deep Aerospace Blue)
        const skyGrad = ctx.createLinearGradient(0, -height * 2, 0, 0);
        skyGrad.addColorStop(0, "#082b4c");
        skyGrad.addColorStop(1, "#125b98");
        ctx.fillStyle = skyGrad;
        ctx.fillRect(-width * 2, -height * 2, width * 4, height * 2);

        // Draw Ground (Rich Earth Slate)
        const groundGrad = ctx.createLinearGradient(0, 0, 0, height * 2);
        groundGrad.addColorStop(0, "#3e2723");
        groundGrad.addColorStop(1, "#1b1412");
        ctx.fillStyle = groundGrad;
        ctx.fillRect(-width * 2, 0, width * 4, height * 2);

        // Horizon White Divider
        ctx.strokeStyle = "#ffffff";
        ctx.lineWidth = 2.5;
        ctx.beginPath();
        ctx.moveTo(-width * 2, 0);
        ctx.lineTo(width * 2, 0);
        ctx.stroke();

        // Pitch Ladder Lines (±10°, ±20°, ±30°)
        ctx.strokeStyle = "rgba(255, 255, 255, 0.75)";
        ctx.fillStyle = "rgba(255, 255, 255, 0.85)";
        ctx.lineWidth = 1.5;
        ctx.font = "10px JetBrains Mono";
        ctx.textAlign = "center";

        const pitchSteps = [-30, -20, -10, 10, 20, 30];
        pitchSteps.forEach(deg => {
            const y = -deg * 3.5;
            const lineLen = Math.abs(deg) % 20 === 0 ? 50 : 30;
            ctx.beginPath();
            ctx.moveTo(-lineLen, y);
            ctx.lineTo(lineLen, y);
            ctx.stroke();
            ctx.fillText(`${deg}°`, lineLen + 14, y + 3);
            ctx.fillText(`${deg}°`, -lineLen - 14, y + 3);
        });

        ctx.restore();

        // Bank Angle Pointer at top
        ctx.save();
        ctx.translate(cx, 25);
        ctx.strokeStyle = "#ffb300";
        ctx.lineWidth = 2;
        ctx.beginPath();
        ctx.arc(0, 0, 20, Math.PI * 0.8, Math.PI * 1.2);
        ctx.stroke();
        ctx.restore();

        requestAnimationFrame(renderHorizon);
    }

    requestAnimationFrame(renderHorizon);
}

// ==============================================================================
// WebSocket Telemetry Connection
// ==============================================================================
function connectWebSocket() {
    if (ws) {
        ws.close();
    }

    const wsUrl = currentDroneId ? `${defaultWsUrl}/${currentDroneId}` : defaultWsUrl;
    setConnectionStatus("CONNECTING...", "connecting");

    ws = new WebSocket(wsUrl);

    ws.onopen = () => {
        isConnected = true;
        setConnectionStatus("ONLINE", "online");
        logTerminal("Connected to live telemetry streaming channel.", "info-line");
    };

    ws.onmessage = (event) => {
        try {
            const msg = JSON.parse(event.data);
            handleIncomingPacket(msg);
        } catch (e) {
            console.error("Packet parse error:", e);
        }
    };

    ws.onerror = (err) => {
        setConnectionStatus("ERROR", "offline");
    };

    ws.onclose = () => {
        isConnected = false;
        setConnectionStatus("DISCONNECTED", "offline");
        logTerminal("Telemetry connection lost. Reconnecting in 3s...", "term-line");
        setTimeout(connectWebSocket, 3000);
    };
}

function setConnectionStatus(text, statusClass) {
    connectionStatusText.innerText = text;
    systemStatusPill.className = `system-status-pill ${statusClass}`;
}

// ==============================================================================
// Inbound Packet Dispatcher
// ==============================================================================
function handleIncomingPacket(packet) {
    packetCount++;
    packetsThisSecond++;
    packetCountVal.innerText = packetCount.toLocaleString();

    // Auto-populate vehicle selector if new drone seen
    if (packet.drone_id && !droneExistsInSelector(packet.drone_id)) {
        addDroneToSelector(packet.drone_id, packet.drone_id);
    }

    // Consolidated State Updates
    if (packet.state) {
        applyConsolidatedState(packet.state);
    }

    // Raw Packet Terminal Log
    if (!isPaused && packet.msg_type) {
        logTerminal(`[${packet.msg_type}] ${JSON.stringify(packet.data || {})}`, getMsgTypeColorClass(packet.msg_type));
    }
}

function applyConsolidatedState(st) {
    // Armed & Flight Mode
    armedBadge.className = `hud-badge armed-badge ${st.armed ? "armed" : "disarmed"}`;
    armedBadge.innerText = st.armed ? "ARMED" : "DISARMED";

    flightModeBadge.innerText = `MODE: ${st.flight_mode || "UNKNOWN"}`;
    landedBadge.innerText = st.landed_state || (st.armed ? "AIRBORNE" : "GROUND");

    // Attitude
    if (st.roll_deg !== undefined && st.roll_deg !== null) {
        targetAttitude.roll = st.roll_deg;
        targetAttitude.pitch = st.pitch_deg || 0;
        targetAttitude.yaw = st.yaw_deg || 0;
        attitudeAngleText.innerText = `R: ${st.roll_deg.toFixed(1)}° | P: ${(st.pitch_deg || 0).toFixed(1)}°`;
    }

    // PFD Tapes
    if (st.airspeed !== undefined && st.airspeed !== null) {
        pfdAirspeedVal.innerText = st.airspeed.toFixed(1);
    }
    if (st.alt_msl !== undefined && st.alt_msl !== null) {
        pfdAltitudeVal.innerText = st.alt_msl.toFixed(1);
    }
    if (st.heading !== undefined && st.heading !== null) {
        headingVal.innerText = Math.round(st.heading).toString().padStart(3, "0");
    }

    // Gauges
    if (st.groundspeed !== undefined && st.groundspeed !== null) {
        groundspeedVal.innerText = st.groundspeed.toFixed(1);
        groundspeedBar.style.width = `${Math.min(100, (st.groundspeed / 30) * 100)}%`;
    }
    if (st.relative_alt !== undefined && st.relative_alt !== null) {
        relativeAltVal.innerText = st.relative_alt.toFixed(1);
        altitudeBar.style.width = `${Math.min(100, (st.relative_alt / 120) * 100)}%`;
    }
    if (st.climb !== undefined && st.climb !== null) {
        climbVal.innerText = (st.climb >= 0 ? "+" : "") + st.climb.toFixed(1);
        const climbPct = Math.max(0, Math.min(100, 50 + (st.climb / 10) * 50));
        climbBar.style.width = `${climbPct}%`;
    }
    if (st.throttle !== undefined && st.throttle !== null) {
        throttleVal.innerText = st.throttle;
        throttleBar.style.width = `${st.throttle}%`;
    }

    // Map Coordinates
    if (st.lat !== undefined && st.lon !== undefined && st.lat !== null && st.lon !== null) {
        updateDroneMapPosition(st.lat, st.lon, st.heading);
    }

    // Power
    if (st.voltage !== undefined && st.voltage !== null) {
        voltageVal.innerHTML = `${st.voltage.toFixed(1)} <small>V</small>`;
    }
    if (st.current !== undefined && st.current !== null) {
        currentVal.innerHTML = `${st.current.toFixed(1)} <small>A</small>`;
    }
    if (st.battery_pct !== undefined && st.battery_pct !== null) {
        batteryPctBadge.innerText = `${st.battery_pct}%`;
        batteryLevelBar.style.width = `${st.battery_pct}%`;
    }
    if (st.cell_voltages && Array.isArray(st.cell_voltages)) {
        renderCellVoltages(st.cell_voltages);
    }

    // GPS & RSSI
    if (st.gps_fix_type) {
        gpsFixBadge.innerText = st.gps_fix_type;
    }
    if (st.satellites !== undefined) {
        satsVal.innerText = st.satellites;
    }
    if (st.hdop !== undefined && st.hdop !== null) {
        hdopVal.innerText = st.hdop.toFixed(2);
    }
    if (st.rc_rssi !== undefined && st.rc_rssi !== null) {
        rssiVal.innerText = `${st.rc_rssi}%`;
        rssiBar.style.width = `${st.rc_rssi}%`;
    }

    // Packet Rate (Hz)
    if (st.packet_rate_hz !== undefined) {
        streamRateVal.innerHTML = `${st.packet_rate_hz.toFixed(1)} <small>Hz</small>`;
    }
}

function renderCellVoltages(cells) {
    cellVoltagesGrid.innerHTML = "";
    cells.forEach((v, idx) => {
        const pill = document.createElement("div");
        pill.className = "cell-pill";
        pill.innerHTML = `C${idx + 1}: <span>${v.toFixed(2)}</span>V`;
        cellVoltagesGrid.appendChild(pill);
    });
}

function getMsgTypeColorClass(type) {
    if (type === "ATTITUDE") return "attitude";
    if (type.includes("POSITION") || type.includes("GPS")) return "position";
    if (type.includes("STATUS") || type.includes("BATTERY")) return "status";
    if (type === "HEARTBEAT") return "heartbeat";
    return "term-line";
}

function logTerminal(text, cls = "term-line") {
    const line = document.createElement("div");
    line.className = `term-line ${cls}`;
    line.innerText = `> ${new Date().toLocaleTimeString()} ${text}`;
    packetTerminal.prepend(line);

    // Keep max 80 elements to prevent DOM bloat
    if (packetTerminal.children.length > 80) {
        packetTerminal.removeChild(packetTerminal.lastChild);
    }
}

// ==============================================================================
// REST API Helpers
// ==============================================================================
async function loadDronesList() {
    try {
        const res = await fetch(`${apiBaseUrl}/drones`);
        if (!res.ok) return;
        const drones = await res.json();
        droneSelector.innerHTML = '<option value="">All Vehicles (Global Stream)</option>';
        drones.forEach(d => {
            addDroneToSelector(d.id, `${d.name} (${d.status})`);
        });
        if (drones.length > 0 && !currentDroneId) {
            currentDroneId = drones[0].id;
            droneSelector.value = currentDroneId;
        }
    } catch (e) {
        console.warn("Could not fetch drones list:", e);
    }
}

function droneExistsInSelector(id) {
    for (let opt of droneSelector.options) {
        if (opt.value === id) return true;
    }
    return false;
}

function addDroneToSelector(id, label) {
    const opt = document.createElement("option");
    opt.value = id;
    opt.textContent = label;
    droneSelector.appendChild(opt);
}

// ==============================================================================
// Timers & Event Handlers
// ==============================================================================
function initUptimeTimer() {
    setInterval(() => {
        // Stream rate calculation fallback
        streamRateVal.innerHTML = `${packetsThisSecond} <small>Hz</small>`;
        packetsThisSecond = 0;

        // Flight Uptime
        const elapsed = Math.floor((Date.now() - flightStartTime) / 1000);
        const hrs = Math.floor(elapsed / 3600).toString().padStart(2, "0");
        const mins = Math.floor((elapsed % 3600) / 60).toString().padStart(2, "0");
        const secs = (elapsed % 60).toString().padStart(2, "0");
        flightTimerVal.innerText = `${hrs}:${mins}:${secs}`;
    }, 1000);
}

function initEventHandlers() {
    droneSelector.addEventListener("change", (e) => {
        currentDroneId = e.target.value;
        flightCoordinates.length = 0;
        flightPathPolyline.setLatLngs([]);
        connectWebSocket();
    });

    centerDroneBtn.addEventListener("click", () => {
        if (flightCoordinates.length > 0) {
            map.panTo(flightCoordinates[flightCoordinates.length - 1]);
        }
    });

    clearPathBtn.addEventListener("click", () => {
        flightCoordinates.length = 0;
        flightPathPolyline.setLatLngs([]);
    });

    pauseLogBtn.addEventListener("click", () => {
        isPaused = !isPaused;
        pauseLogBtn.innerText = isPaused ? "RESUME" : "PAUSE";
    });

    historyModalBtn.addEventListener("click", () => {
        statsModal.style.display = "flex";
        loadFlightStats();
    });

    closeModalBtn.addEventListener("click", () => {
        statsModal.style.display = "none";
    });

    fetchHistoryBtn.addEventListener("click", loadFlightHistory);
}

async function loadFlightStats() {
    if (!currentDroneId) return;
    try {
        const res = await fetch(`${apiBaseUrl}/drones/${currentDroneId}/stats`);
        if (!res.ok) return;
        const stats = await res.json();
        document.getElementById("statDuration").innerText = `${stats.duration_seconds}s`;
        document.getElementById("statMaxAlt").innerText = `${stats.max_altitude_m} m`;
        document.getElementById("statMaxSpeed").innerText = `${stats.max_groundspeed_mps} m/s`;
        document.getElementById("statTotalPts").innerText = stats.total_points.toLocaleString();
    } catch (e) {
        console.error("Stats load error:", e);
    }
}

async function loadFlightHistory() {
    if (!currentDroneId) return;
    try {
        fetchHistoryBtn.innerText = "LOADING...";
        const res = await fetch(`${apiBaseUrl}/drones/${currentDroneId}/history?limit=100`);
        if (!res.ok) return;
        const historyData = await res.json();
        historyTable.innerHTML = "";
        
        if (historyData.items.length === 0) {
            historyTable.innerHTML = '<tr><td colspan="7" style="text-align: center;">No points logged yet.</td></tr>';
            return;
        }

        historyData.items.forEach(item => {
            const tr = document.createElement("tr");
            const timeStr = new Date(item.timestamp).toLocaleTimeString();
            tr.innerHTML = `
                <td>${timeStr}</td>
                <td><strong>${item.msg_type}</strong></td>
                <td>${item.lat ? item.lat.toFixed(5) : "--"}</td>
                <td>${item.lon ? item.lon.toFixed(5) : "--"}</td>
                <td>${item.alt ? item.alt.toFixed(1) : "--"}</td>
                <td>${item.groundspeed ? item.groundspeed.toFixed(1) : "--"}</td>
                <td>${item.battery_pct !== null && item.battery_pct !== undefined ? item.battery_pct + "%" : "--"}</td>
            `;
            historyTable.appendChild(tr);
        });
    } catch (e) {
        console.error("History fetch error:", e);
    } finally {
        fetchHistoryBtn.innerText = "FETCH RECENT 100 RECORDS";
    }
}
