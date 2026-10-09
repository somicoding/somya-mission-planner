let ws = null;
let isConnected = false;


const xValueEl = document.getElementById('xValue');
const yValueEl = document.getElementById('yValue');
const zValueEl = document.getElementById('zValue');
const statusBadge = document.getElementById('statusBadge');
const errorMsg = document.getElementById('errorMsg');
const mapPreview = document.getElementById('mapPreview');
const connectBtn = document.getElementById('connectBtn');
const disconnectBtn = document.getElementById('disconnectBtn');
const connectionUrl = document.getElementById('connectionUrl');


function flashElement(element) {
    element.classList.add('updating');
    setTimeout(() => element.classList.remove('updating'), 300);
}


function updateValue(element, value, unit = '') {
    if (value === undefined || value === null) return;
    const displayValue = value.toFixed(6) + unit;
    if (element.innerText !== displayValue) {
        flashElement(element);
        element.innerText = displayValue;
    }
}

function updateZValue(element, value, unit = '') {
    if (value === undefined || value === null) return;
    const displayValue = value.toFixed(2) + unit;
    if (element.innerText !== displayValue) {
        flashElement(element);
        element.innerText = displayValue;
    }
}

function updateMapPreview(lat, lon, alt) {
    if (lat && lon && alt !== undefined) {
        mapPreview.innerHTML = ` Current Position: ${lat.toFixed(6)}°, ${lon.toFixed(6)}° @ ${alt.toFixed(1)}m altitude`;
    }
}


function connectToWebSocket(url) {
    try {
        if (ws) {
            ws.close();
            ws = null;
        }
        
        ws = new WebSocket(url);
        
        ws.onopen = () => {
            console.log("WebSocket connected!");
            statusBadge.innerHTML = " Connected";
            statusBadge.className = "status-badge status-connected";
            isConnected = true;
            if (errorMsg) errorMsg.innerText = "";
            mapPreview.innerHTML = " Connected to bridge. Waiting for data...";
        };
        
        ws.onmessage = (event) => {
            try {
                const data = JSON.parse(event.data);
                console.log("Data received:", data);
                
               
                if (data.lon !== undefined) {
                    updateValue(xValueEl, data.lon, '°');
                }
               
                if (data.lat !== undefined) {
                    updateValue(yValueEl, data.lat, '°');
                }
                
               
                if (data.alt !== undefined) {
                    updateZValue(zValueEl, data.alt, ' m');
                }
                
              
                if (data.lat && data.lon && data.alt !== undefined) {
                    updateMapPreview(data.lat, data.lon, data.alt);
                }
            } catch (e) {
                console.log('Error parsing data:', e, 'Raw data:', event.data);
            }
        };
        
        ws.onerror = (error) => {
            console.error("WebSocket error:", error);
            statusBadge.innerHTML = " Connection Error";
            statusBadge.className = "status-badge status-disconnected";
            if (errorMsg) errorMsg.innerText = "Connection error. Make sure the bridge is running!";
            mapPreview.innerHTML = "Connection error. Check if bridge is running.";
            isConnected = false;
        };
        
        ws.onclose = () => {
            console.log("WebSocket closed");
            if (isConnected) {
                statusBadge.innerHTML = " Disconnected";
                statusBadge.className = "status-badge status-disconnected";
                isConnected = false;
                if (errorMsg) errorMsg.innerText = "Connection closed";
                mapPreview.innerHTML = "🔌 Disconnected. Click Connect to reconnect.";
            }
        };
    } catch (e) {
        console.error("Failed to connect:", e);
        if (errorMsg) errorMsg.innerText = "Failed to connect: " + e.message;
        mapPreview.innerHTML = "❌ Connection failed";
    }
}


if (connectBtn) {
    connectBtn.onclick = () => {
        if (errorMsg) errorMsg.innerText = "";
        const url = connectionUrl ? connectionUrl.value.trim() : "ws://127.0.0.1:8765";
        
        if (url.startsWith('ws://') || url.startsWith('wss://')) {
            connectToWebSocket(url);
        } else {
            if (errorMsg) errorMsg.innerText = "Please enter a valid WebSocket URL (ws:// or wss://)";
        }
    };
} 


if (disconnectBtn) {
    disconnectBtn.onclick = () => {
        if (ws) {
            ws.close();
            ws = null;
        }
        statusBadge.innerHTML = "Disconnected";
        statusBadge.className = "status-badge status-disconnected";
        isConnected = false;
        if (errorMsg) errorMsg.innerText = "";
       
        if (xValueEl) xValueEl.innerText = '--';
        if (yValueEl) yValueEl.innerText = '--';
        if (zValueEl) zValueEl.innerText = '--';
        if (mapPreview) mapPreview.innerHTML = '🗺️ Waiting for connection...';
    };
}

console.log("Ready - click Connect to connect to WebSocket bridge");    // bridge.js - BACKEND (runs in Node.js on Command Prompt)
const net = require('net');
const WebSocket = require('ws');

const TCP_PORT = 5760;
const WS_PORT = 8765;

let currentData = { lat: null, lon: null, alt: null };

// Connect to Mission Planner's TCP stream
const tcpClient = net.createConnection({ port: TCP_PORT, host: '127.0.0.1' }, () => {
    console.log('✅ Connected to Mission Planner on TCP port ' + TCP_PORT);
    console.log('📡 Waiting for GPS data...');
});

// Parse MAVLink data from Mission Planner
tcpClient.on('data', (buffer) => {
    for (let i = 0; i < buffer.length; i++) {
        if (buffer[i] === 0xFE) {
            const msgId = buffer[i + 5];
            if (msgId === 33 && buffer.length >= i + 28) {
                const lat = buffer.readInt32LE(i + 12) / 1e7;
                const lon = buffer.readInt32LE(i + 16) / 1e7;
                const alt = buffer.readInt32LE(i + 20) / 1000;
                
                currentData = { lat, lon, alt };
                
                // Send JSON to all connected web browsers
                wss.clients.forEach(client => {
                    if (client.readyState === WebSocket.OPEN) {
                        client.send(JSON.stringify(currentData));
                    }
                });
                
                console.log('📍 LAT: ' + lat.toFixed(7) + ' | LON: ' + lon.toFixed(7) + ' | ALT: ' + alt.toFixed(1) + 'm');
            }
        }
    }
});

tcpClient.on('error', (err) => {
    console.error('❌ TCP Error:', err.message);
    console.log('Make sure Mission Planner is connected to the drone.');
});

// WebSocket server for your HTML page
const wss = new WebSocket.Server({ port: WS_PORT });
console.log('🌐 WebSocket server ready on port ' + WS_PORT);
console.log('🔌 Connect your HTML page to: ws://localhost:' + WS_PORT);