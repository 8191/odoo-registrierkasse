from odoo import api, models, fields, _
from odoo.exceptions import UserError

from .libs.a_trust.a_trust_library import SessionData, OrderData, LoginData
from .utils.order_utils import chain_hash, format_order_date
from .utils.revenue_counter import encrypt_revenue_counter


class CustomPOSOrder(models.Model):
    _inherit = 'pos.order'

    encrypted_revenue = fields.Char('Encrypted revenue counter', readonly=True)
    order_signature = fields.Char('Signature from signing unit', readonly=True)
    prev_order_signature = fields.Char('Signature of the previous invoice', readonly=True)
    machine_readable_code = fields.Char('Machine readable code of RKSV', readonly=True)
    certificate_serial_number = fields.Char('Serial number of the certificate', readonly=True)
    registrierkasse_receipt_number = fields.Integer('Sequence of receipt specific to RKSV', readonly=True, copy=False, index=True)

    sum_vat_normal = fields.Float('RKSV VAT Normal', digits=(16, 2), readonly=True, copy=False, required=True, default=0.0, help="VAT 20%")
    sum_vat_discounted_1 = fields.Float('RKSV VAT Discounted 1', digits=(16, 2), copy=False, readonly=True, required=True, default=0.0, help="VAT 10%")
    sum_vat_discounted_2 = fields.Float('RKSV VAT Discounted 2', digits=(16, 2), copy=False, readonly=True, required=True, default=0.0, help="VAT 13%")
    sum_vat_null = fields.Float('RKSV VAT Null', digits=(16, 2), copy=False, readonly=True, required=True, default=0.0, help="VAT 0%")
    sum_vat_special = fields.Float('RKSV VAT Special', digits=(16, 2), copy=False, readonly=True, required=True, default=0.0)
    sum_total_rksv = fields.Float('RKSV Total Sum', digits=(16, 2), copy=False, readonly=True, required=True, default=0.0)

    rksv_state = fields.Selection(
        [('pending', 'Pending'), ('signed', 'Signed'), ('not_signed', 'Not signed'), ('cancel', 'Cancelled')],
        'RKSV Status', readonly=True, copy=False)

    def _generate_pos_reference(self, order):
        """Generate a consistent pos_reference for an order."""
        order_sequence_in_session = self.search_count([('session_id', '=', order.session_id.id)])
        return (f"{_('Order')} {order.session_id.id:05d}-{order_sequence_in_session:03d}-{order.registrierkasse_receipt_number:04d}")

    def _get_rksv_signature(self, config, order_vals, is_refund=False):
        """Helper method to perform RKSV signing."""
        if "sum_total_rksv" in order_vals:
            config.revenue_counter += order_vals.get('sum_total_rksv', 0.0) * 100.0
        else:
            config.revenue_counter += order_vals.get('amount_total', 0.0) * 100.0

        receipt_number = int(config.receipt_sequence_id.next_by_id())

        prev_order = self.env['pos.order'].search(
            [('registrierkasse_receipt_number', '=', int(receipt_number) - 1),
             ('config_id', '=', config.id)], limit=1)

        if is_refund:
            encrypted_revenue = "U1RP"  # Storno
        else:
            encrypted_revenue = encrypt_revenue_counter(
                config.revenue_counter,
                config.registrierkasse_aes_key,
                config.name,
                receipt_number
            )

        # ALWAYS use the current server time for the signature to ensure chronological order
        # regardless of when the order was created (e.g. parked orders).
        current_time = fields.Datetime.now()
        date_order_str = fields.Datetime.to_string(current_time)

        prev_order_signature = chain_hash(prev_order)

        machine_readable_code = OrderData(
            config.name,
            str(receipt_number),
            format_order_date(date_order_str),
            order_vals.get("sum_vat_normal", 0.0),
            order_vals.get("sum_vat_discounted_1", 0.0),
            order_vals.get("sum_vat_discounted_2", 0.0),
            order_vals.get("sum_vat_null", 0.0),
            order_vals.get("sum_vat_special", 0.0),
            encrypted_revenue,
            config.certificate_serial_number,
            prev_order_signature
        ).parse()

        try:
            atrust_api = config.get_atrust_provider()
            a_trust_session_data_obj = SessionData(config.a_trust_session_key, config.a_trust_session_id)
            order_signature = atrust_api.create_signature(a_trust_session_data_obj, machine_readable_code)
        except PermissionError:
            atrust_api = config.get_atrust_provider()
            a_trust_login_session = atrust_api.login(LoginData(config.a_trust_user_name, config.a_trust_password))
            config.write({
                'a_trust_session_key': a_trust_login_session.sessionKey,
                'a_trust_session_id': a_trust_login_session.sessionId
            })
            a_trust_session_data_obj_retry = SessionData(a_trust_login_session.sessionKey,
                                                         a_trust_login_session.sessionId)
            order_signature = atrust_api.create_signature(a_trust_session_data_obj_retry, machine_readable_code)

        return {
            'encrypted_revenue': encrypted_revenue,
            'order_signature': order_signature,
            'machine_readable_code': machine_readable_code,
            'certificate_serial_number': config.certificate_serial_number,
            'prev_order_signature': prev_order_signature,
            'registrierkasse_receipt_number': receipt_number,
            'date_order': date_order_str,
        }

    def _compute_rksv_sums(self, lines):
        sums = {
            'sum_vat_normal': 0.0,
            'sum_vat_discounted_1': 0.0,
            'sum_vat_discounted_2': 0.0,
            'sum_vat_null': 0.0,
            'sum_vat_special': 0.0,
        }

        for line in lines:
            price = line.price_subtotal_incl
            taxes = line.tax_ids

            if taxes:
                first_tax = taxes[0]
                amount = first_tax.amount

                if amount == 20:
                    sums['sum_vat_normal'] += price
                elif amount == 10:
                    sums['sum_vat_discounted_1'] += price
                elif amount == 13:
                    sums['sum_vat_discounted_2'] += price
                elif amount == 0:
                    sums['sum_vat_null'] += price
                else:
                    sums['sum_vat_special'] += price
            else:
                sums['sum_vat_null'] += price

        return sums

    def _is_rksv_refund(self, lines):
        is_refund = True
        for line in lines:
            refunded = line.refunded_orderline_id
            if not refunded:
                is_refund = False
                break
        return is_refund

    @api.model
    def sign_order(self, order_data_dict, is_refund):
        session_id = order_data_dict.get('session_id')
        if not isinstance(session_id, int):
            return {'error': 'Invalid session_id in order_data_dict'}

        session = self.env['pos.session'].browse(session_id)
        if not session.exists():
            return {'error': f'Session {session_id} not found.'}

        config = session.config_id
        if not config.exists() or not config.pos_use_registrierkasse:
            return {'rksv_signed': False, 'message': 'RKSV not active for this POS'}

        if not config.exists() or not config.pos_use_registrierkasse:
            return {'rksv_signed': False, 'message': 'RKSV not active for this POS'}

        return self._get_rksv_signature(config, order_data_dict, is_refund=is_refund)

    @api.model
    def _process_order(self, *args, **kwargs):
        order_id = super()._process_order(*args, **kwargs)
        order_rec = self.browse(order_id)

        if order_rec and order_rec.registrierkasse_receipt_number:
            new_ref = self._generate_pos_reference(order_rec)
            order_rec.write({'pos_reference': new_ref})

        return order_id

    def _prepare_refund_values(self, current_session):
        self.ensure_one()
        values = super()._prepare_refund_values(current_session)
        values.update({
            'registrierkasse_receipt_number': None,
            'order_signature': None,
            'prev_order_signature': None,
            'machine_readable_code': None,
            'encrypted_revenue': None,
            'certificate_serial_number': None,
        })
        return values

    def _process_saved_order(self, draft):
        res = super()._process_saved_order(draft)
        self.action_retry_signing()
        return res

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            session = self.env['pos.session'].browse(vals['session_id'])
            if session.config_id.pos_use_registrierkasse:
                match vals.get('state', 'draft'):
                    case _ if vals.get('registrierkasse_receipt_number'):
                        vals['rksv_state'] = 'signed'
                    case 'draft':
                        vals['rksv_state'] = 'pending'
                    case 'cancel':
                        vals['rksv_state'] = 'cancel'
                    case _:
                        vals['rksv_state'] = 'not_signed'
            else:
                vals['rksv_state'] = None
        return super().create(vals_list)

    def write(self, vals):
        for order in self:
            if vals.get('registrierkasse_receipt_number'):
                vals['rksv_state'] = 'signed'
            elif not order.registrierkasse_receipt_number:
                match vals.get('state'):
                    case 'cancel':
                        vals['rksv_state'] = 'cancel'
                    case 'paid' | 'done' | 'invoiced':
                        vals['rksv_state'] = 'not_signed'
        return super().write(vals)

    def unlink(self):
        """Prevent deletion of RKSV-signed orders."""
        for order in self:
            if order.registrierkasse_receipt_number:
                raise UserError(
                    _('Eine bereits mit der Registrierkasse (RKSV) signierte Bestellung kann nicht gelöscht werden. Bitte erstellen Sie stattdessen eine Erstattung.'))
        return super(CustomPOSOrder, self).unlink()

    def action_retry_signing(self):
        """Manually retry signing the order."""
        for order in self:
            if order.registrierkasse_receipt_number:
                continue  # Already signed

            config = order.session_id.config_id
            if not config.pos_use_registrierkasse:
                continue

            # Calculate sums from existing order lines
            sums = self._compute_rksv_sums(order.lines)

            # Check is_refund
            is_refund = self._is_rksv_refund(order.lines)

            order_vals = {
                'sum_total_rksv': order.amount_total,
                **sums
            }

            try:
                rksv_data = self._get_rksv_signature(config, order_vals, is_refund=is_refund)
                order.write(order_vals | rksv_data)
            except Exception as e:
                raise UserError(_("Signing failed: %s") % str(e))
