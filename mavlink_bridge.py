import asyncio
import json
import websockets
from pymavlink import mavutil

# Configuration
MISSION_PLANNER_TCP_PORT = 5760
WEBSOCKET_PORT = 8765

# Latest telemetry values
latest_telemetry = {
    'lat': -35.3633,
    'lon': 149.1652,
    'alt': 0.0
}

def read_mavlink_data():
    """Read data from Mission Planner in a separate thread"""
    global latest_telemetry
    
    try:
        # Connect to Mission Planner's TCP stream
        print(f"🔄 Connecting to Mission Planner on port {MISSION_PLANNER_TCP_PORT}...")
        master = mavutil.mavlink_connection(f'tcp:127.0.0.1:{MISSION_PLANNER_TCP_PORT}')
        print("✅ Connected to Mission Planner!")
        
        while True:
            # Wait for GPS position message
            msg = master.recv_match(type='GLOBAL_POSITION_INT', blocking=True)
            if msg:
                # Convert to human-readable format
                latest_telemetry['lat'] = msg.lat / 10000000.0
                latest_telemetry['lon'] = msg.lon / 10000000.0
                latest_telemetry['alt'] = msg.alt / 1000.0
                
                print(f"📍 X: {latest_telemetry['lon']:.6f} | Y: {latest_telemetry['lat']:.6f} | Z: {latest_telemetry['alt']:.2f}m")
                
    except Exception as e:
        print(f"❌ Error: {e}")
        print("Make sure Mission Planner is running and connected to SITL!")
        print("Also check that Mission Planner shows 'TCP' connected at the top-right corner")

async def websocket_handler(websocket):
    """Send telemetry to connected web clients"""
    print(f"🌐 Browser connected!")
    try:
        while True:
            await websocket.send(json.dumps(latest_telemetry))
            await asyncio.sleep(0.1)  # 10 updates per second
    except websockets.exceptions.ConnectionClosed:
        print(f"🔌 Browser disconnected")

async def main():
    """Start the WebSocket server"""
    # Start MAVLink reader in background thread
    loop = asyncio.get_event_loop()
    loop.run_in_executor(None, read_mavlink_data)
    
    # Start WebSocket server
    async with websockets.serve(websocket_handler, "127.0.0.1", WEBSOCKET_PORT):
        print(f"\n🚀 WebSocket bridge running!")
        print(f"📡 Connect your HTML page to: ws://127.0.0.1:{WEBSOCKET_PORT}")
        print("Press Ctrl+C to stop\n")
        await asyncio.Future()  # Run forever

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 Bridge stopped")
