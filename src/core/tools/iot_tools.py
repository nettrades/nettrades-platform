# -*- coding: utf-8 -*-
# =============================================================================
# IoT Tools – MQTT subscriber for sensor data streams.
# =============================================================================
import json, logging, os
import paho.mqtt.client as mqtt

_logger = logging.getLogger(__name__)

MQTT_BROKER = os.getenv("IOT_MQTT_BROKER", "mosquitto")
MQTT_PORT = int(os.getenv("IOT_MQTT_PORT", "1883"))

_latest_values: dict = {}


def _on_message(client, userdata, msg):
    try:
        payload = json.loads(msg.payload.decode())
        _latest_values[msg.topic] = payload
    except json.JSONDecodeError:
        _latest_values[msg.topic] = msg.payload.decode()


_client = mqtt.Client(client_id="nettrades-iot")
_client.on_message = _on_message


def start_mqtt_subscriber():
    _client.connect(MQTT_BROKER, MQTT_PORT, keepalive=60)
    _client.subscribe("#")
    _client.loop_start()
    _logger.info("MQTT subscriber started on %s:%d", MQTT_BROKER, MQTT_PORT)


def stop_mqtt_subscriber():
    _client.loop_stop()
    _client.disconnect()


async def get_iot_value(topic: str):
    return _latest_values.get(topic, {"error": "no data"})