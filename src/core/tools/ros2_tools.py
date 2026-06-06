# -*- coding: utf-8 -*-
# =============================================================================
# ROS 2 Tools – wrapper for robot communication via MCP-to-ROS bridge.
# =============================================================================
import os, httpx, logging

_logger = logging.getLogger(__name__)

ROS2_BRIDGE_URL = os.getenv("ROS2_BRIDGE_URL", "http://localhost:5001/mcp")


async def move_arm(joint: str, position: float, speed: float = 1.0):
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{ROS2_BRIDGE_URL}/tools/move_arm",
            json={"joint": joint, "position": position, "speed": speed},
            timeout=30
        )
        return resp.json()


async def navigate_to(x: float, y: float, z: float = 0.0):
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{ROS2_BRIDGE_URL}/tools/navigate",
            json={"x": x, "y": y, "z": z},
            timeout=60
        )
        return resp.json()


async def get_sensor_data(sensor_name: str):
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{ROS2_BRIDGE_URL}/tools/sensor/{sensor_name}",
            timeout=10
        )
        return resp.json()