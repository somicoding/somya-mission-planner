import pytest
from collector.connection import MavlinkConnection

def test_parse_connection_endpoint_windows_serial():
    # Windows COM port with serial: prefix and baud rate
    device, baud = MavlinkConnection.parse_connection_endpoint("serial:COM5:57600", 115200)
    assert device == "COM5"
    assert baud == 57600

    # Windows COM port with serial: prefix without baud rate
    device, baud = MavlinkConnection.parse_connection_endpoint("serial:COM5", 115200)
    assert device == "COM5"
    assert baud == 115200

    # Windows COM port without prefix, with colon baud rate
    device, baud = MavlinkConnection.parse_connection_endpoint("COM5:115200", 57600)
    assert device == "COM5"
    assert baud == 115200

    # Windows plain COM port
    device, baud = MavlinkConnection.parse_connection_endpoint("COM5", 115200)
    assert device == "COM5"
    assert baud == 115200

def test_parse_connection_endpoint_linux_serial():
    # Linux tty with serial: prefix
    device, baud = MavlinkConnection.parse_connection_endpoint("serial:/dev/ttyACM0:115200", 57600)
    assert device == "/dev/ttyACM0"
    assert baud == 115200

    # Linux tty path directly
    device, baud = MavlinkConnection.parse_connection_endpoint("/dev/ttyUSB0", 115200)
    assert device == "/dev/ttyUSB0"
    assert baud == 115200

def test_parse_connection_endpoint_network():
    # UDP in should preserve udpin: prefix and host:port
    device, baud = MavlinkConnection.parse_connection_endpoint("udpin:127.0.0.1:14550", 115200)
    assert device == "udpin:127.0.0.1:14550"
    assert baud == 115200

    # TCP should preserve tcp: prefix
    device, baud = MavlinkConnection.parse_connection_endpoint("tcp:192.168.1.10:5760", 115200)
    assert device == "tcp:192.168.1.10:5760"
    assert baud == 115200
