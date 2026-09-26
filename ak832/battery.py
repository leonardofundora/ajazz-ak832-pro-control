"""Keyboard battery level over Bluetooth (standard 0x180F service). Read-only."""

import plistlib
import subprocess
import sys

BATTERY_SERVICE = "0000180f-0000-1000-8000-00805f9b34fb"
BATTERY_LEVEL = "00002a19-0000-1000-8000-00805f9b34fb"


def read_battery(ble_address=None):
    """Percentage 0-100, or None if it can't be read."""
    try:
        if sys.platform == "win32" and ble_address:
            return _read_windows(int(ble_address, 16))
        if sys.platform == "darwin":
            return _read_mac()
    except Exception:  # noqa: BLE001 - battery is informational only
        return None
    return None


def _read_windows(address):
    import asyncio
    from uuid import UUID

    from winrt.windows.devices.bluetooth import BluetoothCacheMode, BluetoothLEDevice

    async def go():
        dev = await BluetoothLEDevice.from_bluetooth_address_async(address)
        if dev is None:
            return None
        sr = await dev.get_gatt_services_for_uuid_with_cache_mode_async(UUID(BATTERY_SERVICE),
                                                                         BluetoothCacheMode.CACHED)
        if not sr.services:
            return None
        cr = await sr.services[0].get_characteristics_for_uuid_with_cache_mode_async(UUID(BATTERY_LEVEL),
                                                                                   BluetoothCacheMode.CACHED)
        if not cr.characteristics:
            return None
        rr = await cr.characteristics[0].read_value_with_cache_mode_async(BluetoothCacheMode.UNCACHED)
        return bytes(rr.value)[0] if rr.value and rr.value.length else None

    return asyncio.run(go())


def _read_mac():
    # macOS publishes Bluetooth keyboard battery levels in the IOKit registry.
    out = subprocess.run(["ioreg", "-r", "-a", "-k", "BatteryPercent"], capture_output=True, timeout=5).stdout
    if not out:
        return None
    for d in plistlib.loads(out):
        name = str(d.get("Product", ""))
        if "AK832" in name.upper() or (d.get("VendorID") == 0x05AC and d.get("ProductID") == 0x024F):
            return int(d["BatteryPercent"])
    return None
