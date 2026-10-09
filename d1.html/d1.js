(function() {
        // ---- DOM refs ----
        const statusDot = document.getElementById('statusDot');
        const connectionStatusText = document.getElementById('connectionStatusText');
        const xValue = document.getElementById('xValue');
        const yValue = document.getElementById('yValue');
        const zValue = document.getElementById('zValue');
        const speedDisplay = document.getElementById('speedDisplay');
        const gpsStatus = document.getElementById('gpsStatus');
        const takeoffBtn = document.getElementById('takeoffBtn');
        const landBtn = document.getElementById('landBtn');
        const connectBtn = document.getElementById('connectBtn');
        const disconnectBtn = document.getElementById('disconnectBtn');

        // ---- state ----
        let connected = false;
        let telemetryInterval = null;
        let simData = {
            x: 0,        // longitude
            y: 0,        // latitude
            z: 0,        // altitude
            speed: 0,
        };

        // ---- helpers ----
        function updateUI() {
            xValue.textContent = simData.x.toFixed(4);
            yValue.textContent = simData.y.toFixed(4);
            zValue.textContent = simData.z.toFixed(1);
            speedDisplay.innerHTML = `${simData.speed.toFixed(1)} <span class="speed-unit">m/s</span>`;
        }

        function updateGpsStatus(text) {
            gpsStatus.textContent = text;
        }

        function setConnectionState(state) {
            connected = state;
            if (connected) {
                statusDot.className = 'dot connected';
                connectionStatusText.textContent = 'Connected';
                updateGpsStatus('GPS Coordinates: 37.7749°N, 122.4194°W · 3D fix');
                // enable buttons
                takeoffBtn.disabled = false;
                landBtn.disabled = false;
            } else {
                statusDot.className = 'dot';
                connectionStatusText.textContent = 'Disconnected';
                updateGpsStatus('GPS Coordinates: Waiting for connection...');
                takeoffBtn.disabled = true;
                landBtn.disabled = true;
                // reset data to dashes
                xValue.textContent = '--';
                yValue.textContent = '--';
                zValue.textContent = '--';
                speedDisplay.innerHTML = `0.0 <span class="speed-unit">m/s</span>`;
                simData.x = 0; simData.y = 0; simData.z = 0; simData.speed = 0;
            }
        }

        // ---- simulate telemetry (only when connected) ----
        function startTelemetrySim() {
            if (telemetryInterval) clearInterval(telemetryInterval);
            telemetryInterval = setInterval(() => {
                if (!connected) {
                    // if disconnected, clear values but keep showing dashes (already handled)
                    return;
                }
                // // generate some fake movement
                // const t = Date.now() / 1000;
                // // longitude (x) moves slowly, latitude (y) slight drift, altitude (z) with small variation
                // simData.x = -122.4194 + 0.003 * Math.sin(t * 0.1) + 0.001 * Math.sin(t * 0.3);
                // simData.y = 37.7749 + 0.002 * Math.cos(t * 0.12) + 0.0015 * Math.sin(t * 0.22);
                // // altitude between 5 and 25 meters (simulate flight)
                // const altBase = 12 + 7 * Math.sin(t * 0.08);
                // simData.z = Math.max(0, altBase);
                // // speed: 0.5 ~ 4.5 m/s
                // simData.speed = 1.8 + 1.8 * Math.sin(t * 0.15) + 0.6 * Math.cos(t * 0.4);
                // if (simData.speed < 0.2) simData.speed = 0.5;

                // updateUI();

                // update gps status with fake coordinates
                // const lon = simData.x.toFixed(4);
                // const lat = simData.y.toFixed(4);
            //     updateGpsStatus(`GPS Coordinates: ${lat}°N, ${lon}°W · 3D fix`);
            }, 300);
        }

        // ---- connection / disconnection ----
        function connect() {
            if (connected) return;
            // simulate connection handshake
            setConnectionState(true);
            // start telemetry
            startTelemetrySim();
            // update gps
            // updateGpsStatus('GPS Coordinates: 37.7749°N, 122.4194°W · 3D fix');
            // enable buttons
            takeoffBtn.disabled = false;
            landBtn.disabled = false;
        }

        function disconnect() {
            if (!connected) return;
            setConnectionState(false);
            if (telemetryInterval) {
                clearInterval(telemetryInterval);
                telemetryInterval = null;
            }
            // reset display
            xValue.textContent = '--';
            yValue.textContent = '--';
            zValue.textContent = '--';
            speedDisplay.innerHTML = `0.0 <span class="speed-unit">m/s</span>`;
            updateGpsStatus('GPS Coordinates: Waiting for connection...');
            takeoffBtn.disabled = true;
            landBtn.disabled = true;
        }

        // ---- button actions ----
        function handleTakeoff() {
            if (!connected) {
                alert('Connect to Pixhawk telemetry first.');
                return;
            }
            // Simulate takeoff: set altitude to ~10m and show feedback
            // simData.z = 10.0 + Math.random() * 2;
            // simData.speed = 2.5 + Math.random() * 1.2;
            // updateUI();
            updateGpsStatus(`TAKEOFF · alt ${simData.z.toFixed(1)}m · armed`);
            // blink effect
            takeoffBtn.style.transform = 'scale(0.97)';
            setTimeout(() => takeoffBtn.style.transform = '', 150);
            console.log('[TAKEOFF] Drone armed, climbing.');
        }

        function handleLand() {
            if (!connected) {
                alert('Connect to Pixhawk telemetry first.');
                return;
            }
            // Simulate landing: descend & reduce speed
            // simData.z = Math.max(0.5, simData.z - 6 + Math.random() * 3);
            // simData.speed = Math.max(0.3, simData.speed - 1.5 + Math.random() * 0.8);
            // if (simData.z < 1.0) simData.z = 0.8;
            // updateUI();
            updateGpsStatus(` LANDING · alt ${simData.z.toFixed(1)}m`);
            landBtn.style.transform = 'scale(0.97)';
            setTimeout(() => landBtn.style.transform = '', 150);
            console.log('[LAND] Return to launch, descending.');
        }

        // ---- event listeners ----
        connectBtn.addEventListener('click', connect);
        disconnectBtn.addEventListener('click', disconnect);
        takeoffBtn.addEventListener('click', handleTakeoff);
        landBtn.addEventListener('click', handleLand);

        // ---- initial state ----
        setConnectionState(false);
        takeoffBtn.disabled = true;
        landBtn.disabled = true;
        // start with empty data
        xValue.textContent = '--';
        yValue.textContent = '--';
        zValue.textContent = '--';
        speedDisplay.innerHTML = `0.0 <span class="speed-unit">m/s</span>`;
        updateGpsStatus('GPS Coordinates: Waiting for connection...');

        
    })();