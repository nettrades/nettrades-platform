# src/core/tools/ros2_tools.py

class ROS2Tools:
    def collect_robot_data(self, topic, data):
        """Collect data from ROS 2 topics for self-improvement."""
        # For robotics, data_collection_robot collects:
        # - Success/failure of actions
        # - Sensor data for edge cases
        # - Performance metrics (latency, accuracy)

        self.env['data.episode'].create({
            'source': 'ros2',
            'input_text': json.dumps(data),
            'output_text': f"Action on {topic}",
            'quality_score': data.get('success', 0.0),
            'is_qualified': data.get('success', False),
            'context_data': {
                'topic': topic,
                'timestamp': fields.Datetime.now().isoformat(),
            },
        })