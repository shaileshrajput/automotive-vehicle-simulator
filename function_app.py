import azure.functions as func
import json
import logging
from datetime import datetime, timezone

app = func.FunctionApp()


# LAB-ONLY synthetic thresholds.
# These are NOT real automotive safety limits.
BATTERY_WARNING_TEMP_C = 35.0
MOTOR_WARNING_TEMP_C = 65.0


def utc_now():
    return datetime.now(timezone.utc).isoformat()


@app.event_hub_message_trigger(
    arg_name="event",
    event_hub_name="evh-vehicle-telemetry-dev",
    connection="EventHubConnection"
)
def ProcessWarningEvent(event: func.EventHubEvent):

    # ---------------------------------------------------------
    # 1. Read Event Hub message
    # ---------------------------------------------------------
    try:
        message = event.get_body().decode("utf-8")
        telemetry = json.loads(message)

    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        logging.error(
            "Invalid telemetry message: %s",
            error
        )
        return

    # ---------------------------------------------------------
    # 2. Extract required telemetry
    # ---------------------------------------------------------
    vehicle_id = telemetry.get("vehicleId")
    battery_temp = telemetry.get("batteryTemperatureC")
    motor_temp = telemetry.get("motorTemperatureC")

    # ---------------------------------------------------------
    # 3. Validate input
    # ---------------------------------------------------------
    if (
        vehicle_id is None
        or battery_temp is None
        or motor_temp is None
    ):
        logging.warning(
            "Telemetry rejected: required fields are missing."
        )
        return

    # ---------------------------------------------------------
    # 4. Apply deterministic warning rules
    # ---------------------------------------------------------
    battery_warning = (
        battery_temp >= BATTERY_WARNING_TEMP_C
    )

    motor_warning = (
        motor_temp >= MOTOR_WARNING_TEMP_C
    )

    # ---------------------------------------------------------
    # 5. Ignore normal telemetry
    # ---------------------------------------------------------
    if not battery_warning and not motor_warning:

        logging.info(
            "NORMAL | "
            "vehicle=%s | "
            "batteryTemp=%s C | "
            "motorTemp=%s C",
            vehicle_id,
            battery_temp,
            motor_temp
        )

        return

    # ---------------------------------------------------------
    # 6. Create normalized vehicle-health-warning
    # ---------------------------------------------------------
    warning_event = {
        "schemaVersion": "1.0",
        "eventType": "vehicle-health-warning",

        "vehicleId": vehicle_id,

        "severity": "warning",

        "sourceTimestamp": telemetry.get("timestamp"),

        "processedTimestamp": utc_now(),

        "alerts": {
            "batteryTemperatureWarning": battery_warning,
            "motorTemperatureWarning": motor_warning
        },

        "vehicleState": {
            "speedKph": telemetry.get("speedKph"),

            "batterySocPercent": telemetry.get(
                "batterySocPercent"
            ),

            "batteryTemperatureC": battery_temp,

            "motorTemperatureC": motor_temp,

            "odometerKm": telemetry.get(
                "odometerKm"
            ),

            "charging": telemetry.get(
                "charging"
            )
        }
    }

    # ---------------------------------------------------------
    # 7. Log normalized warning
    # ---------------------------------------------------------
    logging.warning(
        "VEHICLE_HEALTH_WARNING | %s",
        json.dumps(warning_event)
    )
