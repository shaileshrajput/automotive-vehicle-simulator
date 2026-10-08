import json
import os
import random
import time
from datetime import datetime, timezone

from azure.iot.device import IoTHubDeviceClient, Message


DEVICE_ID = "VEH-001"
VEHICLE_TYPE = "BEV"

CONNECTION_STRING = os.getenv("IOTHUB_DEVICE_CONNECTION_STRING")

if not CONNECTION_STRING:
    raise RuntimeError(
        "IOTHUB_DEVICE_CONNECTION_STRING is not configured."
    )


def generate_telemetry():
    """Generate synthetic BEV telemetry for lab use."""

    return {
        "vehicleId": DEVICE_ID,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "speedKph": random.randint(0, 110),
        "batterySocPercent": random.randint(40, 95),
        "batteryTemperatureC": round(random.uniform(24.0, 40.0), 1),
        "motorTemperatureC": round(random.uniform(35.0, 75.0), 1),
        "odometerKm": round(random.uniform(12800.0, 12900.0), 1),
        "charging": False,
    }


client = IoTHubDeviceClient.create_from_connection_string(
    CONNECTION_STRING
)

try:
    print(f"Connecting {DEVICE_ID} to Azure IoT Hub...")

    client.connect()

    print(f"{DEVICE_ID} connected successfully.")

    while True:
        telemetry = generate_telemetry()

        payload = json.dumps(telemetry)

        message = Message(payload)
        message.content_type = "application/json"
        message.content_encoding = "utf-8"

        # Application metadata
        message.custom_properties["vehicleType"] = VEHICLE_TYPE
        message.custom_properties["telemetryType"] = "vehicle-status"

        client.send_message(message)

        print(
            f"Sent telemetry: "
            f"speed={telemetry['speedKph']} km/h, "
            f"SOC={telemetry['batterySocPercent']}%, "
            f"battery={telemetry['batteryTemperatureC']} C"
        )

        time.sleep(10)

except KeyboardInterrupt:
    print("\nVEH-001 simulator stopped.")

finally:
    client.disconnect()
    print("Disconnected from Azure IoT Hub.")