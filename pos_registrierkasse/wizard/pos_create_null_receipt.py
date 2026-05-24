import logging

from odoo import fields, models, _
from odoo.api import UserError


_logger = logging.getLogger(__name__)


class PosCreateNullReceiptWizard(models.TransientModel):
    _name = 'pos.nullreceipt.wizard'
    _description = 'Creates a null receipt in the RSKV register'

    def _default_config(self):
        config_id = self.env.context.get('active_id')
        if config_id:
            _logger.debug("Context %s", config_id)
            return self.env['pos.config'].browse(config_id)
        return False

    config_id = fields.Many2one('pos.config', string='Point of Sale Configuration', required=True, default=_default_config)
    description = fields.Text("Description", help="Provide a reason for the null receipt.")

    def create_receipt(self):
        if not self.config_id.pos_use_registrierkasse:
            raise UserError(_("This function is only available for PoS with enabled RKSV."))

        order = self.config_id.create_null_receipt(self.description)
        if order:
            return {
                'type': 'ir.actions.act_window',
                'res_model': 'pos.order',
                'views': [[False, "form"]],
                'res_id': order.id,
            }
        else:
            raise UserError(_("Null receipt could not be created."))