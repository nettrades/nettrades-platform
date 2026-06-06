# -*- coding: utf-8 -*-
# =============================================================================
# NETTRADES GPU Admin – Multi-Modal & Edge-Device Configuration
# =============================================================================
# This transient model (res.config.settings) holds system-wide toggles for
# multimodal inferencing, robotics, and IoT features.  Each feature requires
# the administrator to explicitly enable it.  All features default to False.
# =============================================================================
from odoo import fields, models

class MultimodalConfig(models.TransientModel):
    _name = 'multimodal.config'
    _inherit = 'res.config.settings'

    # ── Multi-Modal Inferencing ──
    enable_multimodal = fields.Boolean(
        string='Enable Multi-Modal Inferencing',
        default=False,
        config_parameter='nettrades.enable_multimodal',
    )
    multimodal_vlm_model = fields.Char(
        string='Default VLM Model',
        default='Qwen2-VL-7B-Instruct',
        config_parameter='nettrades.multimodal_vlm_model',
    )
    multimodal_vlm_endpoint = fields.Char(
        string='VLM Inference Endpoint',
        config_parameter='nettrades.multimodal_vlm_endpoint',
    )

    # ── Robotics Integration ──
    enable_robotics = fields.Boolean(
        string='Enable Robotics Integration',
        default=False,
        config_parameter='nettrades.enable_robotics',
    )
    robotics_ros2_master_uri = fields.Char(
        string='ROS 2 Master URI',
        default='http://localhost:11311',
        config_parameter='nettrades.robotics_ros2_master_uri',
    )
    robotics_vla_model = fields.Char(
        string='Default VLA Model',
        config_parameter='nettrades.robotics_vla_model',
    )

    # ── IoT Integration ──
    enable_iot = fields.Boolean(
        string='Enable IoT Integration',
        default=False,
        config_parameter='nettrades.enable_iot',
    )
    iot_mqtt_broker = fields.Char(
        string='MQTT Broker Host',
        default='mosquitto',
        config_parameter='nettrades.iot_mqtt_broker',
    )
    iot_mqtt_port = fields.Integer(
        string='MQTT Broker Port',
        default=1883,
        config_parameter='nettrades.iot_mqtt_port',
    )

    # ── Edge Device Deployment ──
    enable_edge_deployment = fields.Boolean(
        string='Enable Edge Device Support',
        default=False,
        config_parameter='nettrades.enable_edge_deployment',
    )
    edge_default_quantization = fields.Selection([
        ('q4_k_m', '4-bit (Q4_K_M) – recommended'),
        ('q5_k_m', '5-bit (Q5_K_M)'),
        ('q8_0', '8-bit (Q8_0)'),
    ], string='Default Quantization', default='q4_k_m',
       config_parameter='nettrades.edge_default_quantization',
    )