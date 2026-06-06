# ... inside the controller ...
    def _infer_field(self, question):
        if not question:
            return None
        try:
            return self._call_llm_for_field(question)
        except Exception as e:
            _logger.warning("Field inference failed: %s", e)
            return None

    def _call_llm_for_field(self, question):
        url = request.env['ir.config_parameter'].sudo().get_param(
            'langgraph_invoke_url', 'http://langgraph:8000/invoke')
        api_key = request.env['ir.config_parameter'].sudo().get_param('langgraph_api_key', '')
        payload = {"input": {"messages": [{"role": "user", "content": f"Which professional field does this question belong to? Question: {question}"}]}}
        headers = {'Content-Type': 'application/json'}
        if api_key:
            headers['x-api-key'] = api_key
        import requests
        resp = requests.post(url, json=payload, headers=headers, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        field_name = data.get('analysis', '').strip().lower()
        field = request.env['nettrades.field'].search([('name', 'ilike', field_name)], limit=1)
        return field.id if field else None

    def _match_experts(self, field_id, user_lat, user_lon, requester_id):
        # ... existing matching logic (no external calls, fine)
        ...