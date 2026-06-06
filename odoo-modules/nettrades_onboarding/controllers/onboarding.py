import json, io, logging
import pdfplumber
from odoo import http
from odoo.http import request

_logger = logging.getLogger(__name__)

class OnboardingController(http.Controller):
    @http.route('/api/parse_cv', type='http', auth='user', methods=['POST'], csrf=False)
    def parse_cv(self):
        """Upload a CV file and receive structured extracted data."""
        cv_file = request.httprequest.files.get('cv')
        if not cv_file:
            return request.make_response(json.dumps({'error': 'No file'}),
                                         headers=[('Content-Type', 'application/json')])
        try:
            with pdfplumber.open(io.BytesIO(cv_file.read())) as pdf:
                text = "\n".join(page.extract_text() or '' for page in pdf.pages)
        except Exception:
            return request.make_response(json.dumps({'error': 'Could not read PDF'}),
                                         headers=[('Content-Type', 'application/json')])
        # Call LangGraph (simplified)
        result = {"skills": ["Python", "Django"], "summary": "Experienced developer."}
        return request.make_response(json.dumps(result),
                                     headers=[('Content-Type', 'application/json')])