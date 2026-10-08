import azure.functions as func
import json
import logging

app = func.FunctionApp()

# LAB-ONLY synthetic thresholds.
# These are NOT real automotive safety limits.
BATTERY_WARNING_TEMP_C = 35.0
MOTOR_WARNING_TEMP_C = 65.0


@app.event_hub_message_trigger(
    arg_name="event",
    event_hub_name="evh-vehicle-telemetry-dev",
    connection="EventHubConnection"
)
def ProcessWarningEvent(event: func.EventHubEvent):

    # ---------------------------------------------------------
    # 1. Read and parse telemetry
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
    # 3. Validate required fields
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
    # 4. Evaluate warning rules
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
    # 6. Process warning telemetry
    # ---------------------------------------------------------
    warning_event = {
        "eventType": "vehicle-health-warning",
        "vehicleId": vehicle_id,
        "sourceTimestamp": telemetry.get("timestamp"),
        "severity": "warning",

        "alerts": {
            "batteryTemperatureWarning": battery_warning,
            "motorTemperatureWarning": motor_warning
        },

        "telemetry": {
            "speedKph": telemetry.get("speedKph"),
            "batterySocPercent": telemetry.get(
                "batterySocPercent"
            ),
            "batteryTemperatureC": battery_temp,
            "motorTemperatureC": motor_temp,
            "odometerKm": telemetry.get("odometerKm"),
            "charging": telemetry.get("charging")
        }
    }

    logging.warning(
        "VEHICLE WARNING | %s",
        json.dumps(warning_event)
    )
