# -*- coding: utf-8 -*-
{
    'name': "Austrian Registered Cash Register",
    'version': '18.0.1.1',
    'category': 'Sales/Point Of Sale',
    'summary': "POS Extention to comply with Austrian Registrierkassenpflicht (RKSV)",
    'description': """
        This module makes sure that the point of sales are compliant to Austrian Registrierkassenpflicht (RKSV) Law.
    """,
    'author': "Vorstieg Software FlexCo",
    'website': "https://registrierkasse.vorstieg.eu",
    "maintainer": "Manuel Faux",
    'images': ['images/registrierkasse_thumbnail.png'],
    'depends': ['base', 'point_of_sale', 'l10n_at'],
    'data': [
        'security/ir.model.access.csv',
        'data/pos_order_data.xml',
        'wizard/pos_create_null_receipt.xml',
        'views/pos_config.xml',
        'views/point_of_sale_dashboard.xml',
        'views/res_config_settings_view.xml',
        'views/pos_order_views.xml',
    ],
    'assets': {
        'point_of_sale._assets_pos': [
            '/pos_registrierkasse/static/src/**/*',
        ],
    },
    'license': 'LGPL-3',
}
