from odoo import fields, models, _
from odoo.api import UserError


class PosCreateNullReceiptWizard(models.TransientModel):
    _name = 'pos.nullreceipt.wizard'
    _description = 'Creates a null receipt in the RSKV register'

    def _default_config(self):
        match self.env.context.get('active_model'):
            case 'pos.order':
                order_id = self.env.context.get('active_id')
                if order_id:
                    order = self.env['pos.order'].browse(order_id)
                    if order.exists() and order.config_id:
                        return order.config_id
            case 'pos.config':
                config_id = self.env.context.get('active_id')
                if config_id:
                    return self.env['pos.config'].browse(config_id)
        return False

    def _default_description(self):
        description = "Temporary malfunction of the safety device has been resolved."
        if self.env.context.get('active_model') == "pos.order" and self.env.context.get('signed_order_ids'):
            orders = self.env['pos.order'].browse(self.env.context.get('signed_order_ids'))
            description += "\n\nCollective null receipt for following orders:\n" + "\n".join(o.pos_reference for o in orders)
        return description

    config_id = fields.Many2one('pos.config', string='Point of Sale Configuration', required=True, default=_default_config)
    description = fields.Text("Description", help="Provide a reason for the null receipt.", default=_default_description)

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