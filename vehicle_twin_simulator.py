import json
import os
import random
import signal
import sys
import time
from datetime import datetime, timezone
from threading import Event

from azure.iot.device import IoTHubDeviceClient, Message


# ---------------------------------------------------------------------
# Device identity and static simulator metadata
# ---------------------------------------------------------------------

DEVICE_ID = "VEH-001"
VEHICLE_TYPE = "BEV"
SIMULATOR_VERSION = "1.0.0"


# ---------------------------------------------------------------------
# Default configuration
# These values are used when desired properties are missing or invalid.
# ---------------------------------------------------------------------

DEFAULT_TELEMETRY_INTERVAL_SECONDS = 10
MIN_TELEMETRY_INTERVAL_SECONDS = 2
MAX_TELEMETRY_INTERVAL_SECONDS = 300

DEFAULT_MAX_BATTERY_TEMPERATURE_C = 45.0
DEFAULT_MAX_MOTOR_TEMPERATURE_C = 85.0


# ---------------------------------------------------------------------
# Runtime state
# ---------------------------------------------------------------------

runtime_config = {
    "telemetryIntervalSeconds": DEFAULT_TELEMETRY_INTERVAL_SECONDS,
    "targetSoftwareVersion": SIMULATOR_VERSION,
    "maxBatteryTemperatureC": DEFAULT_MAX_BATTERY_TEMPERATURE_C,
    "maxMotorTemperatureC": DEFAULT_MAX_MOTOR_TEMPERATURE_C,
}

vehicle_state = {
    "batterySocPercent": 82.0,
    "odometerKm": 12850.0,
}

stop_event = Event()


# ---------------------------------------------------------------------
# Utility functions
# ---------------------------------------------------------------------

def utc_now():
    return datetime.now(timezone.utc).isoformat()


def clamp(value, minimum, maximum):
    return max(minimum, min(value, maximum))


def get_connection_string():
    connection_string = os.getenv(
        "IOTHUB_DEVICE_CONNECTION_STRING"
    )

    if not connection_string:
        raise RuntimeError(
            "IOTHUB_DEVICE_CONNECTION_STRING is not configured."
        )

    return connection_string


def get_desired_properties(twin):
    """
    Extract the desired-property section returned by the device SDK.
    """

    desired = twin.get("desired")

    if isinstance(desired, dict):
        return desired

    properties = twin.get("properties", {})

    if isinstance(properties, dict):
        desired = properties.get("desired", {})

        if isinstance(desired, dict):
            return desired

    return {}


def validate_interval(value):
    try:
        interval = int(value)
    except (TypeError, ValueError):
        return None

    if not (
        MIN_TELEMETRY_INTERVAL_SECONDS
        <= interval
        <= MAX_TELEMETRY_INTERVAL_SECONDS
    ):
        return None

    return interval


def validate_temperature_threshold(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------
# Twin processing
# ---------------------------------------------------------------------

def apply_desired_properties(client):
    """
    Retrieve desired properties, validate them, apply supported values,
    and report the outcome through reported properties.
    """

    twin = client.get_twin()
    desired = get_desired_properties(twin)

    desired_version = desired.get("$version")

    acknowledgement = {
        "configuration": {
            "lastProcessedUtc": utc_now(),
            "desiredVersion": desired_version,
            "status": "applied",
            "errors": {},
        }
    }

    errors = {}

    # Telemetry interval
    if "telemetryIntervalSeconds" in desired:
        interval = validate_interval(
            desired["telemetryIntervalSeconds"]
        )

        if interval is None:
            errors["telemetryIntervalSeconds"] = (
                "Value must be an integer from "
                f"{MIN_TELEMETRY_INTERVAL_SECONDS} to "
                f"{MAX_TELEMETRY_INTERVAL_SECONDS}."
            )
        else:
            runtime_config["telemetryIntervalSeconds"] = interval

    # Target software version
    if "targetSoftwareVersion" in desired:
        target_version = desired["targetSoftwareVersion"]

        if not isinstance(target_version, str) or not target_version:
            errors["targetSoftwareVersion"] = (
                "Value must be a non-empty string."
            )
        else:
            runtime_config["targetSoftwareVersion"] = target_version

    # Battery temperature threshold
    if "maxBatteryTemperatureC" in desired:
        threshold = validate_temperature_threshold(
            desired["maxBatteryTemperatureC"]
        )

        if threshold is None:
            errors["maxBatteryTemperatureC"] = (
                "Value must be numeric."
            )
        else:
            runtime_config["maxBatteryTemperatureC"] = threshold

    # Motor temperature threshold
    if "maxMotorTemperatureC" in desired:
        threshold = validate_temperature_threshold(
            desired["maxMotorTemperatureC"]
        )

        if threshold is None:
            errors["maxMotorTemperatureC"] = (
                "Value must be numeric."
            )
        else:
            runtime_config["maxMotorTemperatureC"] = threshold

    if errors:
        acknowledgement["configuration"]["status"] = (
            "partially-applied"
        )
        acknowledgement["configuration"]["errors"] = errors

    acknowledgement["configuration"]["applied"] = {
        "telemetryIntervalSeconds": (
            runtime_config["telemetryIntervalSeconds"]
        ),
        "targetSoftwareVersion": (
            runtime_config["targetSoftwareVersion"]
        ),
        "maxBatteryTemperatureC": (
            runtime_config["maxBatteryTemperatureC"]
        ),
        "maxMotorTemperatureC": (
            runtime_config["maxMotorTemperatureC"]
        ),
    }

    client.patch_twin_reported_properties(acknowledgement)

    print("Desired configuration processed:")
    print(json.dumps(acknowledgement, indent=2))


def report_startup_state(client):
    """
    Report relatively stable device capabilities and current status.
    """

    reported = {
        "vehicle": {
            "vehicleType": VEHICLE_TYPE,
            "simulated": True,
        },
        "software": {
            "currentVersion": SIMULATOR_VERSION,
            "targetVersion": runtime_config[
                "targetSoftwareVersion"
            ],
        },
        "capabilities": {
            "batteryTelemetry": True,
            "motorTelemetry": True,
            "locationTelemetry": False,
            "remoteCommands": False,
        },
        "connectivity": {
            "status": "connected",
            "lastConnectedUtc": utc_now(),
        },
        "simulator": {
            "status": "running",
            "version": SIMULATOR_VERSION,
        },
    }

    client.patch_twin_reported_properties(reported)


def report_shutdown_state(client):
    reported = {
        "connectivity": {
            "status": "disconnecting",
            "lastDisconnectedUtc": utc_now(),
        },
        "simulator": {
            "status": "stopped",
            "version": SIMULATOR_VERSION,
        },
    }

    client.patch_twin_reported_properties(reported)


# ---------------------------------------------------------------------
# Synthetic vehicle model
# ---------------------------------------------------------------------

def generate_telemetry():
    """
    Create synthetic BEV telemetry.

    This is lab data and does not represent an actual vehicle.
    """

    speed_kph = random.randint(0, 110)

    battery_temperature_c = round(
        random.uniform(26.0, 48.0),
        1,
    )

    motor_temperature_c = round(
        random.uniform(40.0, 92.0),
        1,
    )

    if speed_kph > 0:
        vehicle_state["batterySocPercent"] = clamp(
            vehicle_state["batterySocPercent"]
            - random.uniform(0.01, 0.08),
            0.0,
            100.0,
        )

        distance_increment = (
            speed_kph
            * runtime_config["telemetryIntervalSeconds"]
            / 3600
        )

        vehicle_state["odometerKm"] += distance_increment

    battery_alert = (
        battery_temperature_c
        > runtime_config["maxBatteryTemperatureC"]
    )

    motor_alert = (
        motor_temperature_c
        > runtime_config["maxMotorTemperatureC"]
    )

    if battery_alert or motor_alert:
        health_status = "warning"
    else:
        health_status = "normal"

    return {
        "schemaVersion": "1.0",
        "messageType": "vehicle-status",
        "vehicleId": DEVICE_ID,
        "timestampUtc": utc_now(),
        "telemetry": {
            "speedKph": speed_kph,
            "batterySocPercent": round(
                vehicle_state["batterySocPercent"],
                2,
            ),
            "batteryTemperatureC": battery_temperature_c,
            "motorTemperatureC": motor_temperature_c,
            "odometerKm": round(
                vehicle_state["odometerKm"],
                3,
            ),
            "charging": False,
        },
        "health": {
            "status": health_status,
            "batteryTemperatureAlert": battery_alert,
            "motorTemperatureAlert": motor_alert,
        },
    }


def send_telemetry(client):
    telemetry = generate_telemetry()

    message = Message(json.dumps(telemetry))
    message.content_type = "application/json"
    message.content_encoding = "utf-8"

    message.custom_properties["telemetryType"] = (
        "vehicle-status"
    )

    message.custom_properties["healthStatus"] = (
        telemetry["health"]["status"]
    )

    client.send_message(message)

    print(
        "Sent telemetry | "
        f"vehicle={DEVICE_ID} | "
        f"speed={telemetry['telemetry']['speedKph']} km/h | "
        f"SOC={telemetry['telemetry']['batterySocPercent']}% | "
        f"battery={telemetry['telemetry']['batteryTemperatureC']} C | "
        f"motor={telemetry['telemetry']['motorTemperatureC']} C | "
        f"health={telemetry['health']['status']}"
    )


# ---------------------------------------------------------------------
# Graceful shutdown
# ---------------------------------------------------------------------

def request_shutdown(signum, frame):
    stop_event.set()


signal.signal(signal.SIGINT, request_shutdown)

if hasattr(signal, "SIGTERM"):
    signal.signal(signal.SIGTERM, request_shutdown)


# ---------------------------------------------------------------------
# Main application
# ---------------------------------------------------------------------

def main():
    connection_string = get_connection_string()

    client = IoTHubDeviceClient.create_from_connection_string(
        connection_string
    )

    try:
        print(f"Connecting {DEVICE_ID} to Azure IoT Hub...")
        client.connect()
        print(f"{DEVICE_ID} connected successfully.")

        # Report initial device state.
        report_startup_state(client)

        # Retrieve and apply existing desired properties.
        apply_desired_properties(client)

        last_twin_refresh = time.monotonic()
        twin_refresh_interval_seconds = 15

        while not stop_event.is_set():
            send_telemetry(client)

            interval = runtime_config[
                "telemetryIntervalSeconds"
            ]

            # Wait without blocking graceful shutdown.
            stop_event.wait(interval)

            # Poll for desired-property changes.
            current_time = time.monotonic()

            if (
                current_time - last_twin_refresh
                >= twin_refresh_interval_seconds
            ):
                apply_desired_properties(client)
                last_twin_refresh = current_time

        print(f"Stopping {DEVICE_ID}...")

        report_shutdown_state(client)

    except Exception as error:
        print(
            f"{DEVICE_ID} simulator failed: "
            f"{type(error).__name__}: {error}",
            file=sys.stderr,
        )
        raise

    finally:
        try:
            client.disconnect()
            print("Disconnected from Azure IoT Hub.")
        except Exception as disconnect_error:
            print(
                "Disconnect warning: "
                f"{disconnect_error}",
                file=sys.stderr,
            )


if __name__ == "__main__":
    main()