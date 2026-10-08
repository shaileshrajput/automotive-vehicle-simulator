import azure.functions as func
import logging

app = func.FunctionApp()

@app.event_hub_message_trigger(
    arg_name="event",
    event_hub_name="evh-vehicle-telemetry-dev",
    connection="EventHubConnection"
)
def ProcessWarningEvent(event: func.EventHubEvent):
    message = event.get_body().decode("utf-8")

    logging.info("VEH-001 telemetry received: %s", message)