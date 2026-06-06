# -*- coding: utf-8 -*-
# Section F.7 – AI Chatbot Widget
{
    'name': 'NETTRADES AI Chatbot',
    'version': '1.0',
    'depends': ['nettrades_core', 'website', 'bus'],
    'data': [
        'views/llm_message_buttons.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'nettrades_chatbot/static/src/js/llm_message_buttons.js',
        ],
    },
    'controllers': ['controllers/chatbot.py'],
    'installable': True,
}