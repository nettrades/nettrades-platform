# src/core/agents/inference_tools.py

def get_inference_route(request_type='inference', request_data=None):
    """
    Get the appropriate inference route for a request.
    Called by LangGraph agents before sending a request.
    """
    # Call Odoo bridge route model via the proxy
    odoo_proxy_url = os.getenv('ODOO_PROXY_URL', 'http://odoo-proxy:8080')
    odoo_api_key = os.getenv('ODOO_API_KEY', '')

    try:
        response = requests.post(
            f'{odoo_proxy_url}/api/bridge/route/decide',
            headers={'X-API-Key': odoo_api_key},
            json={
                'request_type': request_type,
                'request_data': request_data or {},
            },
            timeout=10,
        )
        if response.status_code == 200:
            return response.json()
    except Exception as e:
        _logger.error(f'Error getting route: {e}')

    # Fallback to default
    return {
        'target_url': 'http://llama-cpp:8080/v1',
        'target_type': 'llama_cpp',
        'api_key': '',
        'routing_mode': 'local_only',
    }