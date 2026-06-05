"""Testes de pagamento PIX e comprovante."""
from decimal import Decimal
from unittest.mock import MagicMock, patch

from pizzaria.bot_views import (
    finalize_order_from_draft,
    get_conversation_state,
    handle_awaiting_receipt,
    handle_payment_choice,
    set_conversation_state,
)
from pizzaria.models import Customer, Order, OrderItem
from pizzaria.tests.base import BotTestCase


class PixPaymentTests(BotTestCase):
    def _order_awaiting_payment(self, order_type='PICKUP'):
        customer = Customer.objects.create(name='Cliente PIX', phone=self.PHONE)
        order = Order.objects.create(
            customer=customer,
            order_type=order_type,
            status='AWAITING_PAYMENT',
            subtotal=Decimal('55.00'),
            total=Decimal('55.00'),
        )
        OrderItem.objects.create(
            order=order,
            product=self.products['Calabresa'],
            quantity=1,
            unit_price=Decimal('27.50'),
        )
        OrderItem.objects.create(
            order=order,
            product=self.products['Mussarela'],
            quantity=1,
            unit_price=Decimal('27.50'),
        )
        set_conversation_state(self.PHONE, 'awaiting_payment_choice', {'order_id': order.id})
        return order

    def test_escolhe_pix_aguarda_comprovante(self):
        order = self._order_awaiting_payment()
        msg = handle_payment_choice(self.PHONE, 'pix')
        self.assertIn('comprovante', msg.lower())
        self.assertIn(self.settings.pix_key, msg)

        order.refresh_from_db()
        self.assertEqual(order.payment_method, 'PIX')

        state = get_conversation_state(self.PHONE)
        self.assertEqual(state['state'], 'awaiting_receipt')
        self.assertEqual(state['data']['order_id'], order.id)

    def test_escolhe_dinheiro_pergunta_troco(self):
        order = self._order_awaiting_payment()
        msg = handle_payment_choice(self.PHONE, 'dinheiro')
        self.assertIn('troco', msg.lower())
        order.refresh_from_db()
        self.assertEqual(order.payment_method, 'CASH')
        self.assertEqual(get_conversation_state(self.PHONE)['state'], 'awaiting_change')

    def test_escolhe_cartao_pergunta_tipo(self):
        order = self._order_awaiting_payment()
        msg = handle_payment_choice(self.PHONE, 'cartão')
        self.assertIn('Crédito', msg)
        self.assertEqual(get_conversation_state(self.PHONE)['state'], 'awaiting_card_type')


class ReceiptTests(BotTestCase):
    def _order_awaiting_receipt(self):
        customer = Customer.objects.create(name='Cliente PIX', phone=self.PHONE)
        order = Order.objects.create(
            customer=customer,
            order_type='PICKUP',
            status='AWAITING_PAYMENT',
            payment_method='PIX',
            subtotal=Decimal('40.00'),
            total=Decimal('40.00'),
        )
        OrderItem.objects.create(
            order=order,
            product=self.products['Calabresa'],
            quantity=1,
            unit_price=Decimal('40.00'),
        )
        set_conversation_state(self.PHONE, 'awaiting_receipt', {'order_id': order.id})
        return order

    @patch('pizzaria.bot_views.requests.get')
    def test_comprovante_imagem_confirma(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.content = b'\xff\xd8\xff fake jpeg'
        mock_resp.headers = {'Content-Type': 'image/jpeg'}
        mock_get.return_value = mock_resp

        order = self._order_awaiting_receipt()
        msg = handle_awaiting_receipt(
            self.PHONE,
            '',
            'image',
            media_url='http://localhost:3000/api/files/receipt.jpg',
        )

        order.refresh_from_db()
        self.assertEqual(order.payment_status, 'RECEIPT_RECEIVED')
        self.assertEqual(order.status, 'AWAITING_PAYMENT')
        self.assertTrue(order.payment_receipt.name)
        self.assertIn('Comprovante recebido', msg)
        self.assertEqual(get_conversation_state(self.PHONE)['state'], 'welcome')

    def test_comprovante_tipo_imagem_sem_url(self):
        order = self._order_awaiting_receipt()
        msg = handle_awaiting_receipt(self.PHONE, '', 'image')
        order.refresh_from_db()
        self.assertEqual(order.payment_status, 'RECEIPT_RECEIVED')
        self.assertIn('Comprovante recebido', msg)

    def test_sem_comprovante_lembra_cliente(self):
        self._order_awaiting_receipt()
        msg = handle_awaiting_receipt(self.PHONE, 'oi', 'chat')
        self.assertIn('esperando o comprovante', msg.lower())

    def test_pagar_na_entrega_muda_fluxo(self):
        order = self._order_awaiting_receipt()
        order.order_type = 'DELIVERY'
        order.save()
        msg = handle_awaiting_receipt(self.PHONE, 'pagar na entrega', 'chat')
        self.assertIn('pagamento', msg.lower())
        self.assertEqual(get_conversation_state(self.PHONE)['state'], 'awaiting_payment_method')

    def test_pedir_resumo_enquanto_aguarda(self):
        order = self._order_awaiting_receipt()
        msg = handle_awaiting_receipt(self.PHONE, 'resumo', 'chat')
        self.assertIn('Calabresa', msg)
        self.assertIn('comprovante', msg.lower())

    def test_sem_order_id_limpa_estado(self):
        set_conversation_state(self.PHONE, 'awaiting_receipt', {})
        msg = handle_awaiting_receipt(self.PHONE, '', 'image')
        self.assertIn('deu errado', msg.lower())


class PixEndToEndTests(BotTestCase):
    @patch('pizzaria.bot_views.handle_payment_choice')
    @patch('pizzaria.bot_views.send_whatsapp_message')
    def test_rascunho_sim_dispara_pix(self, mock_send, mock_payment):
        mock_payment.return_value = 'Chave PIX...'
        draft = {
            'items': [{
                'name': 'Calabresa',
                'quantity': 1,
                'product_id': self.products['Calabresa'].id,
                'price': 40.0,
            }],
            'order_type': 'PICKUP',
            'payment_method': 'pix',
            'subtotal': 40.0,
            'delivery_fee': 0,
        }
        set_conversation_state(self.PHONE, 'awaiting_draft_confirmation', {'draft': draft})
        finalize_order_from_draft(self.PHONE, draft)
        mock_payment.assert_called_once_with(self.PHONE, 'pix')

    @patch('pizzaria.bot_views.requests.get')
    def test_fluxo_completo_draft_pix_comprovante(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.content = b'pdf-content'
        mock_resp.headers = {'Content-Type': 'application/pdf'}
        mock_get.return_value = mock_resp

        draft = {
            'items': [{
                'name': 'Calabresa',
                'quantity': 1,
                'product_id': self.products['Calabresa'].id,
                'price': 40.0,
            }],
            'order_type': 'PICKUP',
            'payment_method': 'pix',
            'subtotal': 40.0,
            'delivery_fee': 0,
        }
        set_conversation_state(self.PHONE, 'awaiting_draft_confirmation', {'draft': draft})
        finalize_order_from_draft(self.PHONE, draft)

        state = get_conversation_state(self.PHONE)
        self.assertEqual(state['state'], 'awaiting_receipt')
        order_id = state['data']['order_id']

        msg = handle_awaiting_receipt(
            self.PHONE, '', 'document',
            media_url='http://127.0.0.1:3000/files/proof.pdf',
        )
        order = Order.objects.get(id=order_id)
        self.assertEqual(order.payment_status, 'RECEIPT_RECEIVED')
        self.assertTrue(order.payment_receipt.name.endswith('.pdf'))
        self.assertIn('Comprovante recebido', msg)
