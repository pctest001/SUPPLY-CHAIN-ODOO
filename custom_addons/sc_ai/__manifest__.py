{
    'name': 'Supply Chain AI (MVP)',
    'summary': '对话式供应链助手 / 智能预警解读（LLM + Function Calling）',
    'version': '1.0',
    'license': 'LGPL-3',
    'category': 'AI',
    'depends': ['base', 'supply_chain_demo'],
    'data': [
        'security/ir.model.access.csv',
        'data/ai_config.xml',
        'views/ai_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'sc_ai/static/src/sc_ai.scss',
            'sc_ai/static/src/ai_chat_panel/ai_chat_panel.xml',
            'sc_ai/static/src/ai_chat_panel/ai_chat_panel.js',
            'sc_ai/static/src/sc_ai.js',
        ],
    },
    'installable': True,
    'application': True,
}
