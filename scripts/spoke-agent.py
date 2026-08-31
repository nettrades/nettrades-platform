#!/usr/bin/env python3
# =============================================================================
# NETTRADES Spoke Agent
# =============================================================================
# FILE: scripts/spoke-agent.py
# PURPOSE: Lightweight agent that runs on spoke nodes to:
#          - Register with the sub-hub
#          - Send heartbeats
#          - Pull and execute inference jobs
#          - Report results
#
# This agent has NO dependencies on Odoo, PostgreSQL, or LangGraph.
# It is designed to be extremely lightweight (< 200 MB RAM).
# =============================================================================

import os
import sys
import json
import time
import logging
import argparse
import subprocess
import threading
import signal
from datetime import datetime
from typing import Dict, Any, Optional

import requests
import yaml

# =============================================================================
# Configuration
# =============================================================================

CONFIG_FILE = os.environ.get('SPOKE_CONFIG', '/etc/nettrades/spoke/config.yaml')
LOG_LEVEL = os.environ.get('LOG_LEVEL', 'INFO')

# =============================================================================
# Logging
# =============================================================================

logging.basicConfig(
    level=getattr(logging, LOG_LEVEL),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('spoke-agent')

# =============================================================================
# GPU Detection
# =============================================================================

def detect_gpu() -> Dict[str, Any]:
    """Detect GPU information."""
    gpu_info = {
        'vendor': 'none',
        'model': 'unknown',
        'vram_gb': 0,
        'compute_capability': 'unknown',
    }
    
    # Check NVIDIA
    try:
        result = subprocess.run(
            ['nvidia-smi', '--query-gpu=name,memory.total,compute_cap', '--format=csv,noheader'],
            capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0:
            lines = result.stdout.strip().split('\n')
            if lines:
                parts = lines[0].split(',')
                gpu_info['vendor'] = 'nvidia'
                gpu_info['model'] = parts[0].strip()
                gpu_info['vram_gb'] = float(parts[1].strip().split()[0]) / 1024
                if len(parts) > 2:
                    gpu_info['compute_capability'] = parts[2].strip()
                return gpu_info
    except Exception as e:
        logger.debug(f"NVIDIA detection failed: {e}")
    
    # Check AMD
    try:
        result = subprocess.run(
            ['rocminfo', '--gpu'],
            capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0:
            gpu_info['vendor'] = 'amd'
            # Parse rocminfo output for model and VRAM
            for line in result.stdout.split('\n'):
                if 'Name:' in line:
                    gpu_info['model'] = line.split('Name:')[1].strip()
                if 'Memory Size:' in line:
                    try:
                        gpu_info['vram_gb'] = float(line.split('Memory Size:')[1].strip().split()[0]) / 1024
                    except:
                        pass
            return gpu_info
    except Exception as e:
        logger.debug(f"AMD detection failed: {e}")
    
    # Check Intel
    try:
        result = subprocess.run(
            ['intel_gpu_top', '-J'],
            capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0:
            gpu_info['vendor'] = 'intel'
            # Parse JSON output for model
            try:
                data = json.loads(result.stdout)
                gpu_info['model'] = data.get('device', {}).get('name', 'Intel GPU')
            except:
                pass
            return gpu_info
    except Exception as e:
        logger.debug(f"Intel detection failed: {e}")
    
    return gpu_info

def get_gpu_utilization() -> Dict[str, Any]:
    """Get current GPU utilization."""
    stats = {
        'gpu_utilization': 0,
        'memory_utilization': 0,
        'temperature': 0,
        'is_available': True,
    }
    
    # NVIDIA
    try:
        result = subprocess.run(
            ['nvidia-smi', '--query-gpu=utilization.gpu,memory.used,memory.total,temperature.gpu',
             '--format=csv,noheader'],
            capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0:
            lines = result.stdout.strip().split('\n')
            if lines:
                parts = [p.strip() for p in lines[0].split(',')]
                stats['gpu_utilization'] = float(parts[0].split()[0]) if parts[0] else 0
                stats['memory_utilization'] = float(parts[1].split()[0]) / float(parts[2].split()[0]) * 100 if len(parts) > 2 else 0
                stats['temperature'] = float(parts[3].split()[0]) if len(parts) > 3 else 0
                return stats
    except Exception as e:
        logger.debug(f"NVIDIA utilization failed: {e}")
    
    return stats

# =============================================================================
# Spoke Agent Class
# =============================================================================

class SpokeAgent:
    """Main spoke agent class."""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.sub_hub_url = config.get('sub_hub_url', 'http://localhost:8080')
        self.node_name = config.get('node_name', os.uname().nodename)
        self.heartbeat_interval = config.get('heartbeat_interval', 10)
        self.inference_engine = config.get('inference_engine', 'llama.cpp')
        self.gpu_info = detect_gpu()
        self.node_id = None
        self.registered = False
        self.running = True
        self.job_threads = []
        
        logger.info(f"Spoke Agent initialized")
        logger.info(f"  Node: {self.node_name}")
        logger.info(f"  GPU: {self.gpu_info}")
        logger.info(f"  Sub-hub: {self.sub_hub_url}")
    
    def register(self) -> bool:
        """Register this node with the sub-hub."""
        try:
            data = {
                'name': self.node_name,
                'gpu_model': self.gpu_info.get('model', 'unknown'),
                'vram_gb': self.gpu_info.get('vram_gb', 0),
                'compute_capability': self.gpu_info.get('compute_capability', ''),
                'inference_engine': self.inference_engine,
                'status': 'available',
            }
            response = requests.post(
                f"{self.sub_hub_url}/api/v1/gpu/nodes",
                json=data,
                timeout=10
            )
            if response.status_code == 200:
                result = response.json()
                if result.get('status') == 'success':
                    self.node_id = result.get('data', {}).get('id')
                    self.registered = True
                    logger.info(f"Registered with node ID: {self.node_id}")
                    return True
                else:
                    logger.error(f"Registration failed: {result.get('message')}")
            else:
                logger.error(f"Registration HTTP error: {response.status_code}")
        except Exception as e:
            logger.error(f"Registration error: {e}")
        return False
    
    def heartbeat(self) -> bool:
        """Send a heartbeat to the sub-hub."""
        if not self.registered or not self.node_id:
            return False
        
        try:
            stats = get_gpu_utilization()
            data = {
                'timestamp': datetime.now().isoformat(),
                'gpu_utilization': stats['gpu_utilization'],
                'memory_utilization': stats['memory_utilization'],
                'temperature': stats['temperature'],
                'is_available': stats['is_available'],
            }
            response = requests.post(
                f"{self.sub_hub_url}/api/v1/gpu/nodes/{self.node_id}/heartbeat",
                json=data,
                timeout=10
            )
            if response.status_code == 200:
                logger.debug(f"Heartbeat sent")
                return True
            else:
                logger.warning(f"Heartbeat failed: {response.status_code}")
        except Exception as e:
            logger.error(f"Heartbeat error: {e}")
        return False
    
    def pull_job(self) -> Optional[Dict[str, Any]]:
        """Pull a job from the sub-hub."""
        if not self.registered or not self.node_id:
            return None
        
        try:
            response = requests.get(
                f"{self.sub_hub_url}/api/v1/jobs/assign",
                params={'node_id': self.node_id},
                timeout=10
            )
            if response.status_code == 200:
                result = response.json()
                if result.get('status') == 'success' and result.get('data'):
                    return result['data']
            elif response.status_code == 204:
                # No jobs available
                return None
            else:
                logger.warning(f"Pull job failed: {response.status_code}")
        except Exception as e:
            logger.error(f"Pull job error: {e}")
        return None
    
    def execute_job(self, job: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a job using the inference engine."""
        job_id = job.get('id')
        job_type = job.get('type', 'inference')
        model = job.get('model', '')
        prompt = job.get('prompt', '')
        parameters = job.get('parameters', {})
        
        logger.info(f"Executing job {job_id} (type: {job_type})")
        
        result = {
            'status': 'failed',
            'result': None,
            'error': None,
        }
        
        if job_type == 'inference':
            try:
                # Use llama.cpp or vLLM
                if self.inference_engine == 'llama.cpp':
                    # Call llama.cpp server
                    response = requests.post(
                        'http://localhost:8080/completion',
                        json={
                            'prompt': prompt,
                            'temperature': parameters.get('temperature', 0.7),
                            'max_tokens': parameters.get('max_tokens', 512),
                            'stream': False,
                        },
                        timeout=120
                    )
                    if response.status_code == 200:
                        data = response.json()
                        result['status'] = 'completed'
                        result['result'] = data.get('content', '')
                    else:
                        result['error'] = f"llama.cpp error: {response.status_code}"
                elif self.inference_engine == 'vllm':
                    # Call vLLM server
                    response = requests.post(
                        'http://localhost:8000/v1/completions',
                        json={
                            'model': model,
                            'prompt': prompt,
                            'temperature': parameters.get('temperature', 0.7),
                            'max_tokens': parameters.get('max_tokens', 512),
                        },
                        timeout=120
                    )
                    if response.status_code == 200:
                        data = response.json()
                        result['status'] = 'completed'
                        result['result'] = data.get('choices', [{}])[0].get('text', '')
                    else:
                        result['error'] = f"vLLM error: {response.status_code}"
                else:
                    result['error'] = f"Unknown inference engine: {self.inference_engine}"
            except Exception as e:
                result['error'] = str(e)
                logger.error(f"Job execution error: {e}")
        else:
            result['error'] = f"Unknown job type: {job_type}"
        
        return result
    
    def submit_result(self, job_id: str, result: Dict[str, Any]) -> bool:
        """Submit job result back to the sub-hub."""
        try:
            response = requests.put(
                f"{self.sub_hub_url}/api/v1/jobs/{job_id}",
                json={
                    'status': result.get('status', 'failed'),
                    'result_data': result.get('result'),
                },
                timeout=10
            )
            if response.status_code == 200:
                logger.info(f"Submitted result for job {job_id}")
                return True
            else:
                logger.warning(f"Result submission failed: {response.status_code}")
        except Exception as e:
            logger.error(f"Result submission error: {e}")
        return False
    
    def run_heartbeat_loop(self):
        """Run the heartbeat loop in a separate thread."""
        while self.running:
            if not self.heartbeat():
                # If heartbeat fails, try to re-register
                self.registered = False
                if not self.register():
                    logger.warning("Re-registration failed, waiting...")
                    time.sleep(30)
            time.sleep(self.heartbeat_interval)
    
    def run_job_loop(self):
        """Run the job polling loop."""
        while self.running:
            if not self.registered:
                time.sleep(5)
                continue
            
            job = self.pull_job()
            if job:
                result = self.execute_job(job)
                self.submit_result(job['id'], result)
            else:
                time.sleep(2)
    
    def run(self):
        """Main agent loop."""
        # Register with sub-hub
        if not self.register():
            logger.error("Initial registration failed. Retrying in 30 seconds...")
            time.sleep(30)
            if not self.register():
                logger.error("Registration failed again. Exiting.")
                return
        
        # Start heartbeat thread
        heartbeat_thread = threading.Thread(target=self.run_heartbeat_loop)
        heartbeat_thread.daemon = True
        heartbeat_thread.start()
        
        # Start job thread
        job_thread = threading.Thread(target=self.run_job_loop)
        job_thread.daemon = True
        job_thread.start()
        
        # Wait for termination
        try:
            while self.running:
                time.sleep(1)
        except KeyboardInterrupt:
            logger.info("Shutting down...")
            self.running = False
        
        heartbeat_thread.join(timeout=5)
        job_thread.join(timeout=5)
        logger.info("Spoke agent stopped")

# =============================================================================
# Main
# =============================================================================

def main():
    parser = argparse.ArgumentParser(description='NETTRADES Spoke Agent')
    parser.add_argument('--config', type=str, default=CONFIG_FILE,
                        help='Configuration file path')
    parser.add_argument('--sub-hub', type=str,
                        help='Sub-hub URL (overrides config)')
    parser.add_argument('--node-name', type=str,
                        help='Node name (overrides config)')
    args = parser.parse_args()
    
    # Load configuration
    config = {}
    if os.path.exists(args.config):
        with open(args.config, 'r') as f:
            config = yaml.safe_load(f) or {}
    
    # Override with command line
    if args.sub_hub:
        config['sub_hub_url'] = args.sub_hub
    if args.node_name:
        config['node_name'] = args.node_name
    
    # Validate configuration
    if not config.get('sub_hub_url'):
        logger.error("sub_hub_url is required")
        sys.exit(1)
    
    # Run agent
    agent = SpokeAgent(config)
    agent.run()

if __name__ == '__main__':
    main()