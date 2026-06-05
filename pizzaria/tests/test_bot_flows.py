"""Testes de integração: fluxos do bot com WhatsApp mockado."""
import json
from unittest.mock import patch

from django.core.cache import cache

from pizzaria.bot_views import (
    build_half_half_cart_item,
    clear_conversation_state,
    get_conversation_state,
    handle_partial_order,
    handle_welcome,
    process_n8n_envelope,
    set_conversation_state,
    try_handle_repeat_order,
    try_handle_simple_intent,
)
from pizzaria.order_coverage import (
    entities_to_partial_draft,
    get_missing_fields,
    order_to_draft,
)
from pizzaria.tests.base import BotTestCase


class SimpleIntentFlowTests(BotTestCase):
    @patch('pizzaria.bot_views.send_whatsapp_message')
    def test_saudacao_envia_mensagem(self, mock_send):
        resp = try_handle_simple_intent(self.PHONE, 'oi')
        self.assertIsNotNone(resp)
        mock_send.assert_called_once()
        self.assertEqual(json.loads(resp.content)['action'], 'saudacao')

    @patch('pizzaria.bot_views.send_whatsapp_message')
    def test_cardapio(self, mock_send):
        resp = try_handle_simple_intent(self.PHONE, 'cardápio')
        self.assertEqual(json.loads(resp.content)['action'], 'cardapio')

    @patch('pizzaria.bot_views.send_whatsapp_message')
    def test_nao_intercepta_fora_welcome(self, mock_send):
        set_conversation_state(self.PHONE, 'awaiting_address', {})
        resp = try_handle_simple_intent(self.PHONE, 'oi')
        self.assertIsNone(resp)
        mock_send.assert_not_called()


class RepeatOrderFlowTests(BotTestCase):
    @patch('pizzaria.bot_views.send_whatsapp_buttons')
    def test_repetir_com_historico(self, mock_buttons):
        self.create_customer_with_order()
        resp = try_handle_repeat_order(self.PHONE)
        self.assertEqual(json.loads(resp.content)['action'], 'repeat_order')
        mock_buttons.assert_called_once()
        state = get_conversation_state(self.PHONE)
        self.assertEqual(state['state'], 'awaiting_draft_confirmation')

    @patch('pizzaria.bot_views.send_whatsapp_message')
    def test_repetir_sem_historico(self, mock_send):
        resp = try_handle_repeat_order(self.PHONE)
        self.assertEqual(json.loads(resp.content)['action'], 'no_previous_order')


class HalfHalfFlowTests(BotTestCase):
    @patch('pizzaria.bot_views.send_whatsapp_buttons')
    @patch('pizzaria.bot_views.send_whatsapp_message')
    def test_duas_meio_a_meio_retirada_completa(self, mock_msg, mock_buttons):
        """Pedido só com sabores → pergunta entrega/retirada."""
        msg = 'queria 1 calabresa com metade de frango e outra de queijo com bolonhesa'
        result = handle_welcome(self.PHONE, msg, 'chat')
        self.assertEqual(result, '')
        state = get_conversation_state(self.PHONE)
        self.assertEqual(state['state'], 'awaiting_partial_order')
        self.assertEqual(len(state['data']['partial_draft']['items']), 2)

    def test_build_half_half_cart_item(self):
        item, missing = build_half_half_cart_item('calabresa', 'frango')
        self.assertIsNone(missing)
        self.assertEqual(item['type'], 'half_half')
        self.assertEqual(item['price'], 42.0)

    def test_sabor_inexistente(self):
        item, missing = build_half_half_cart_item('saborxyz', 'frango')
        self.assertIsNone(item)
        self.assertEqual(missing, 'saborxyz')


class PartialOrderFlowTests(BotTestCase):
    def _start_partial(self):
        from pizzaria.bot_views import find_product_fuzzy

        entities = {
            'delivery_type': 'unknown',
            'payment_method': 'unknown',
            'order': {'items': [{'name': 'calabresa', 'quantity': 1}]},
        }
        partial = entities_to_partial_draft(entities, None, find_product_fuzzy)
        waiting = get_missing_fields(partial)[0]
        set_conversation_state(self.PHONE, 'awaiting_partial_order', {
            'partial_draft': partial,
            'waiting_field': waiting,
        })
        return waiting

    @patch('pizzaria.bot_views.send_whatsapp_buttons')
    @patch('pizzaria.bot_views.send_whatsapp_message')
    def test_preenche_campo_por_campo(self, mock_msg, mock_buttons):
        waiting = self._start_partial()
        self.assertEqual(waiting, 'order_type')

        handle_partial_order(self.PHONE, 'retirada')
        state = get_conversation_state(self.PHONE)
        self.assertEqual(state['data']['partial_draft']['order_type'], 'PICKUP')

        handle_partial_order(self.PHONE, 'pix')
        state = get_conversation_state(self.PHONE)
        self.assertEqual(state['state'], 'awaiting_draft_confirmation')
        mock_buttons.assert_called()


class N8nEnvelopeTests(BotTestCase):
    def _envelope(self, text, llm_result=None, used_llm=False, address_resolution=None):
        return {
            'normalized': {
                'phone': self.PHONE,
                'text': text,
                'msg_type': 'chat',
            },
            'buffer': {'combined_text': text},
            'routing': {'used_llm': used_llm, 'reason': 'test'},
            'llm': {
                'valid': True,
                'result': llm_result or {},
            } if used_llm else None,
            'address_resolution': address_resolution,
        }

    @patch('pizzaria.bot_views.send_whatsapp_message')
    def test_router_saudacao_sem_llm(self, mock_send):
        resp = process_n8n_envelope(self._envelope('oi'))
        self.assertEqual(json.loads(resp.content)['action'], 'saudacao')

    @patch('pizzaria.bot_views.send_whatsapp_buttons')
    @patch('pizzaria.bot_views.send_whatsapp_message')
    def test_llm_pedido_parcial(self, mock_msg, mock_buttons):
        llm_result = {
            'intent': 'order_build',
            'entities': {
                'delivery_type': 'unknown',
                'payment_method': 'unknown',
                'order': {'items': [{'name': 'mussarela', 'quantity': 1}]},
            },
        }
        resp = process_n8n_envelope(
            self._envelope('1 mussarela', llm_result=llm_result, used_llm=True)
        )
        data = json.loads(resp.content)
        self.assertEqual(data['action'], 'partial_order')
        self.assertEqual(data['waiting'], 'order_type')

    @patch('pizzaria.bot_views.send_whatsapp_buttons')
    def test_llm_pedido_completo(self, mock_buttons):
        llm_result = {
            'intent': 'order_build',
            'entities': {
                'delivery_type': 'pickup',
                'payment_method': 'pix',
                'order': {'items': [{'name': 'calabresa', 'quantity': 1}]},
            },
        }
        resp = process_n8n_envelope(
            self._envelope('1 calabresa retirada pix', llm_result=llm_result, used_llm=True)
        )
        self.assertEqual(json.loads(resp.content)['action'], 'draft_confirmation')

    @patch('pizzaria.bot_views.send_whatsapp_buttons')
    @patch('pizzaria.bot_views.send_whatsapp_message')
    def test_fallback_meio_a_meio_multi_sem_llm(self, mock_msg, mock_buttons):
        msg = 'queria 1 calabresa com metade de frango e outra de queijo com bolonhesa'
        resp = process_n8n_envelope(
            self._envelope(
                msg,
                llm_result={'intent': 'other', 'entities': {}},
                used_llm=True,
            )
        )
        self.assertEqual(json.loads(resp.content)['action'], 'half_half_multi')
        state = get_conversation_state(self.PHONE)
        self.assertEqual(state['state'], 'awaiting_partial_order')

    @patch('pizzaria.bot_views.process_standard_message')
    def test_estado_prioritario_ignora_llm(self, mock_standard):
        from django.http import JsonResponse
        mock_standard.return_value = JsonResponse({'status': 'ok'})
        set_conversation_state(self.PHONE, 'awaiting_address', {})
        process_n8n_envelope(
            self._envelope(
                'rua teste 1',
                llm_result={'intent': 'other', 'entities': {}},
                used_llm=True,
            )
        )
        mock_standard.assert_called_once()


class OrderToDraftTests(BotTestCase):
    def test_repetir_pedido_anterior(self):
        _, order = self.create_customer_with_order()
        draft = order_to_draft(order)
        self.assertTrue(draft['from_repeat'])
        self.assertEqual(draft['items'][0]['name'], 'Calabresa')
        self.assertEqual(draft['payment_method'], 'pix')
