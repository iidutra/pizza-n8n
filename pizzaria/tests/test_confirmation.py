"""Testes de confirmação de rascunho, confusão e validações."""
from unittest.mock import patch

from django.core.cache import cache

from pizzaria.bot_views import (
    get_conversation_state,
    handle_draft_confirmation,
    is_question,
    is_valid_phone,
    set_conversation_state,
)
from pizzaria.conversational_helpers import (
    increment_confusion_count,
    reset_confusion_count,
    should_simplify_response,
)
from pizzaria.models import Order
from pizzaria.tests.base import BotTestCase
from pizzaria.waha_service import is_valid_chat_id


class DraftConfirmationTests(BotTestCase):
    def _draft_pickup_pix(self):
        return {
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

    @patch('pizzaria.bot_views.send_whatsapp_message')
    def test_sim_cria_pedido(self, mock_send):
        set_conversation_state(self.PHONE, 'awaiting_draft_confirmation', {
            'draft': self._draft_pickup_pix(),
        })
        handle_draft_confirmation(self.PHONE, 'sim')
        self.assertEqual(Order.objects.count(), 1)
        order = Order.objects.first()
        self.assertEqual(order.order_type, 'PICKUP')
        self.assertEqual(order.items.count(), 1)

    @patch('pizzaria.bot_views.send_whatsapp_message')
    def test_nao_limpa_e_pede_de_novo(self, mock_send):
        set_conversation_state(self.PHONE, 'awaiting_draft_confirmation', {
            'draft': self._draft_pickup_pix(),
        })
        msg = handle_draft_confirmation(self.PHONE, 'mudar')
        self.assertIn('Manda de novo', msg)
        state = get_conversation_state(self.PHONE)
        self.assertEqual(state['state'], 'welcome')

    @patch('pizzaria.bot_views.handle_welcome')
    def test_correcao_reprocessa(self, mock_welcome):
        mock_welcome.return_value = 'ok'
        set_conversation_state(self.PHONE, 'awaiting_draft_confirmation', {
            'draft': self._draft_pickup_pix(),
        })
        handle_draft_confirmation(self.PHONE, '2 mussarela retirada pix')
        mock_welcome.assert_called_once()


class ConfusionTests(BotTestCase):
    def test_contador_confusao(self):
        self.assertFalse(should_simplify_response(self.PHONE))
        increment_confusion_count(self.PHONE)
        increment_confusion_count(self.PHONE)
        self.assertTrue(should_simplify_response(self.PHONE))
        reset_confusion_count(self.PHONE)
        self.assertFalse(should_simplify_response(self.PHONE))


class QuestionDetectionTests(BotTestCase):
    def test_perguntas_comuns(self):
        is_q, qtype, _ = is_question('quanto custa a pizza')
        self.assertTrue(is_q)
        self.assertEqual(qtype, 'price')

        is_q, qtype, _ = is_question('quanto tempo demora')
        self.assertTrue(is_q)
        self.assertEqual(qtype, 'time')

        is_q, _, _ = is_question('aceita pix')
        self.assertTrue(is_q)


class ValidationTests(BotTestCase):
    def test_telefone_valido(self):
        self.assertTrue(is_valid_phone('5511999999999'))
        self.assertFalse(is_valid_phone('123'))
        self.assertFalse(is_valid_phone(''))

    def test_chat_id_valido(self):
        self.assertTrue(is_valid_chat_id('5511999999999@c.us'))
        self.assertFalse(is_valid_chat_id('invalid'))
