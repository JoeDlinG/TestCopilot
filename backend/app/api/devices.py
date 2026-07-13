"""Device management API routes.

GET    /api/devices           - List devices (with filters + pagination)
GET    /api/devices/discover  - Discover connected hardware devices
POST   /api/devices           - Create device
GET    /api/devices/{id}      - Get device details
PUT    /api/devices/{id}      - Update device
DELETE /api/devices/{id}      - Delete device
POST   /api/devices/connect   - Connect to device
POST   /api/devices/{id}/disconnect - Disconnect device
POST   /api/devices/{id}/command    - Send command to device
"""
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.exceptions import DeviceNotFoundError, DeviceConnectionError
from app.schemas.schemas import (
    DeviceCreate, DeviceResponse, DeviceUpdate,
    DeviceConnectRequest, DeviceCommandRequest, DeviceCommandResponse,
)
from app.services.device_service import device_service

router = APIRouter(prefix="/api/devices", tags=["Devices"])


@router.get("/discover")
async def discover_devices():
    """Discover connected hardware devices (serial, VISA, CAN, raw USB)."""
    discovered = []
    seen_ports = set()  # Deduplicate

    # Discover serial ports via pyserial
    try:
        import serial.tools.list_ports
        ports = list(serial.tools.list_ports.comports())
        for p in ports:
            port_key = p.device
            if port_key in seen_ports:
                continue
            seen_ports.add(port_key)
            discovered.append({
                "name": p.description or p.device,
                "type": "generic",
                "protocol": "serial",
                "connection_type": "serial",
                "serial_port": p.device,
                "vid": f"{p.vid:04X}" if p.vid else None,
                "pid": f"{p.pid:04X}" if p.pid else None,
                "serial_number": p.serial_number,
                "manufacturer": p.manufacturer,
            })
    except ImportError:
        pass
    except Exception:
        pass

    # Discover raw USB devices via /sys/bus/usb (catches devices without kernel driver)
    # This is critical for STM32 and other devices where cdc_acm may not auto-bind
    try:
        import os
        usb_devices_path = "/sys/bus/usb/devices"
        if os.path.isdir(usb_devices_path):
            for entry in os.listdir(usb_devices_path):
                dev_path = os.path.join(usb_devices_path, entry)
                vendor_path = os.path.join(dev_path, "idVendor")
                product_path = os.path.join(dev_path, "idProduct")
                manufacturer_path = os.path.join(dev_path, "manufacturer")
                product_name_path = os.path.join(dev_path, "product")
                serial_path = os.path.join(dev_path, "serial")
                devnum_path = os.path.join(dev_path, "devnum")

                if not (os.path.isfile(vendor_path) and os.path.isfile(product_path)):
                    continue

                def _read_sysfs(p):
                    try:
                        with open(p, "r") as f:
                            return f.read().strip()
                    except Exception:
                        return None

                vid_str = _read_sysfs(vendor_path)
                pid_str = _read_sysfs(product_path)
                if not vid_str or not pid_str:
                    continue

                try:
                    vid = int(vid_str, 16)
                    pid = int(pid_str, 16)
                except ValueError:
                    continue

                # Skip USB hubs, HID devices, and non-instrument entries
                # Also check bDeviceClass to filter out hubs (09), HID (03), wireless (e0)
                bDeviceClass_path = os.path.join(dev_path, "bDeviceClass")
                bDeviceClass = _read_sysfs(bDeviceClass_path)

                # Skip Linux Foundation devices (root hubs)
                if vid in (0x1d6b,):
                    continue

                # Skip hubs (class 09), HID devices (class 03), and other non-instrument classes
                # Only include: Vendor Specific (ff), Communications (02), or no tty found but potentially interesting
                try:
                    dev_class = int(bDeviceClass, 16) if bDeviceClass else None
                except (ValueError, TypeError):
                    dev_class = None

                # Filter: skip hubs, HID keyboards/mice, mass storage, wireless, etc.
                if dev_class is not None and dev_class in (0x09,):  # Hub
                    continue

                # Skip wireless/bluetooth/misc (class e0)
                if dev_class == 0xe0:
                    continue

                # For class 03 (HID), skip unless it looks like a test instrument
                if dev_class == 0x03:
                    name_check = f"{manufacturer} {product}".lower()
                    if not any(kw in name_check for kw in ("stm", "ftdi", "silabs", "cp210", "ch340", "pl2303", "arduino", "teensy", "test", "instrument", "measure", "scope", "meter", "power", "supply", "signal", "generator", "analyzer", "load", "daq", "gpio")):
                        continue

                # For class 00 (per-interface), check interface classes
                if dev_class == 0x00 or dev_class is None:
                    # Check if any interface is CDC (02) or Vendor Specific (ff)
                    has_relevant_interface = False
                    for subentry in os.listdir(dev_path):
                        sub_path = os.path.join(dev_path, subentry)
                        if os.path.isdir(sub_path) and ":" in subentry:
                            intf_class_path = os.path.join(sub_path, "bInterfaceClass")
                            intf_class = _read_sysfs(intf_class_path)
                            if intf_class in ("02", "0a", "ff"):  # CDC, CDC Data, Vendor Specific
                                has_relevant_interface = True
                                break
                    if not has_relevant_interface:
                        continue

                vid_hex = f"{vid:04X}"
                pid_hex = f"{pid:04X}"
                manufacturer = _read_sysfs(manufacturer_path) or ""
                product = _read_sysfs(product_name_path) or ""
                serial_num = _read_sysfs(serial_path) or ""

                # Try to find the associated tty device
                tty_device = None
                for subentry in os.listdir(dev_path):
                    sub_path = os.path.join(dev_path, subentry)
                    if os.path.isdir(sub_path):
                        for item in os.listdir(sub_path):
                            if item.startswith("tty"):
                                tty_device = f"/dev/{item}"
                                break
                    if tty_device:
                        break

                port_key = tty_device or f"usb:{vid_hex}:{pid_hex}"
                if port_key in seen_ports:
                    continue
                seen_ports.add(port_key)

                name = f"{manufacturer} {product}".strip()
                if not name:
                    name = f"USB Device {vid_hex}:{pid_hex}"

                discovered.append({
                    "name": name,
                    "type": "generic",
                    "protocol": "serial" if tty_device else "usb",
                    "connection_type": "serial" if tty_device else "usb",
                    "serial_port": tty_device,
                    "vid": vid_hex,
                    "pid": pid_hex,
                    "serial_number": serial_num or None,
                    "manufacturer": manufacturer or None,
                    "usb_device_path": f"/dev/bus/usb/{_read_sysfs(os.path.join(dev_path, 'busnum')) or '001'}/{_read_sysfs(devnum_path) or '001'}",
                    "has_kernel_driver": tty_device is not None,
                })
    except Exception:
        pass

    # Discover VISA resources
    try:
        import pyvisa
        rm = pyvisa.ResourceManager()
        resources = rm.list_resources()
        for r in resources:
            if r in seen_ports:
                continue
            seen_ports.add(r)
            discovered.append({
                "name": r,
                "type": "generic",
                "protocol": "scpi",
                "connection_type": "usb",
                "visa_address": r,
            })
        rm.close()
    except ImportError:
        pass
    except Exception:
        pass

    return {"code": 0, "message": "success", "data": discovered}


@router.get("/")
async def list_devices(
    type: Optional[str] = Query(None, alias="type"),
    status: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    devices, total = await device_service.list_devices(
        db, device_type=type, status=status, page=page, page_size=page_size,
    )
    return {
        "code": 0,
        "message": "success",
        "data": {
            "items": [device_service._model_to_response(d) for d in devices],
            "total": total,
            "page": page,
            "page_size": page_size,
        },
    }


@router.post("/", status_code=201)
async def create_device(data: DeviceCreate, db: AsyncSession = Depends(get_db)):
    device = await device_service.create_device(db, data)
    return {
        "code": 0,
        "message": "success",
        "data": device_service._model_to_response(device),
    }


@router.get("/{device_id}")
async def get_device(device_id: str, db: AsyncSession = Depends(get_db)):
    device = await device_service.get_device(db, device_id)
    if not device:
        raise HTTPException(status_code=404, detail={
            "code": 40001, "message": "Device not found",
            "detail": f"No device with id={device_id}",
        })
    return {
        "code": 0,
        "message": "success",
        "data": device_service._model_to_response(device),
    }


@router.put("/{device_id}")
async def update_device(device_id: str, data: DeviceUpdate, db: AsyncSession = Depends(get_db)):
    device = await device_service.update_device(db, device_id, data)
    if not device:
        raise HTTPException(status_code=404, detail={
            "code": 40001, "message": "Device not found",
            "detail": f"No device with id={device_id}",
        })
    return {
        "code": 0,
        "message": "success",
        "data": device_service._model_to_response(device),
    }


@router.delete("/{device_id}")
async def delete_device(device_id: str, db: AsyncSession = Depends(get_db)):
    success = await device_service.delete_device(db, device_id)
    if not success:
        raise HTTPException(status_code=404, detail={
            "code": 40001, "message": "Device not found",
            "detail": f"No device with id={device_id}",
        })
    return {"code": 0, "message": "Device deleted", "data": None}


@router.post("/connect")
async def connect_device(data: DeviceConnectRequest, db: AsyncSession = Depends(get_db)):
    try:
        result = await device_service.connect_device(db, data.device_id, data.config)
        return {"code": 0, "message": "success", "data": result}
    except ValueError as e:
        raise HTTPException(status_code=404, detail={
            "code": 40001, "message": "Device not found", "detail": str(e),
        })
    except Exception as e:
        raise HTTPException(status_code=400, detail={
            "code": 40002, "message": "Connection failed", "detail": str(e),
        })


@router.post("/{device_id}/disconnect")
async def disconnect_device(device_id: str, db: AsyncSession = Depends(get_db)):
    try:
        result = await device_service.disconnect_device(db, device_id)
        return {"code": 0, "message": "success", "data": result}
    except ValueError as e:
        raise HTTPException(status_code=404, detail={
            "code": 40001, "message": "Device not found", "detail": str(e),
        })


@router.post("/{device_id}/command")
async def send_command(
    device_id: str,
    data: DeviceCommandRequest,
    execution_id: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    try:
        result = await device_service.send_command(
            db, device_id, data.command, execution_id=execution_id,
        )
        return {"code": 0, "message": "success", "data": result}
    except (ValueError, ConnectionError) as e:
        raise HTTPException(status_code=400, detail={
            "code": 40002, "message": "Command failed", "detail": str(e),
        })
    except Exception as e:
        raise HTTPException(status_code=400, detail={
            "code": 40002, "message": "Command failed",
            "detail": f"Unexpected error: {str(e)}",
        })
