const { SerialPort } = require('serialport');
const WebSocket = require('ws');

const WS_PORT = 8766;
const COM_PORT = 'COM7';
const BAUD_RATE = 57600;

let currentData = { lat: null, lon: null, alt: null };

const serialPort = new SerialPort({
    path: COM_PORT,
    baudRate: BAUD_RATE,
    autoOpen: true
});

serialPort.on('open', () => {
    console.log('✅ Connected to Pixhawk on ' + COM_PORT);
    console.log('📡 Waiting for REAL GPS data...');
});

serialPort.on('data', (buffer) => {
    for (let i = 0; i < buffer.length; i++) {
        if (buffer[i] === 0xFE) {
            const msgId = buffer[i + 5];
            if (msgId === 33 && buffer.length >= i + 28) {
                const lat = buffer.readInt32LE(i + 12) / 1e7;
                const lon = buffer.readInt32LE(i + 16) / 1e7;
                const alt = buffer.readInt32LE(i + 20) / 1000;
                
                if (lat !== 0 || lon !== 0) {
                    currentData = { lat, lon, alt };
                    
                    wss.clients.forEach(client => {
                        if (client.readyState === WebSocket.OPEN) {
                            client.send(JSON.stringify(currentData));
                        }
                    });
                    
                    console.log('📍 REAL GPS: Lat: ' + lat.toFixed(7) + ' | Lon: ' + lon.toFixed(7) + ' | Alt: ' + alt.toFixed(1) + 'm');
                }
            }
        }
    }
});

serialPort.on('error', (err) => {
    console.error('❌ Serial Error:', err.message);
    console.log('Make sure:');
    console.log('  1. Pixhawk is connected via USB');
    console.log('  2. Mission Planner is NOT using COM7');
    console.log('  3. COM7 is the correct port');
});

const wss = new WebSocket.Server({ port: WS_PORT });
console.log('🌐 WebSocket server ready on port ' + WS_PORT);
console.log('🔌 Connect HTML to: ws://localhost:' + WS_PORT);