"""Testes do fluxo promo (2 por R$55) e integração LLM."""
import json
from decimal import Decimal
from unittest.mock import patch

from pizzaria.bot_views import (
    get_conversation_state,
    handle_confirming_pickup,
    handle_promo_half_or_full,
    handle_promo_more_items,
    handle_promo_order,
    handle_promo_order_type,
    handle_promo_pizza_1,
    handle_promo_request,
    handle_promo_second_after_half,
    process_llm_promo_items,
    process_llm_promo_pairs,
    process_n8n_envelope,
    set_conversation_state,
)
from pizzaria.conversational_helpers import entities_to_draft
from pizzaria.models import Product
from pizzaria.tests.base import BotTestCase


class PromoCatalogMixin:
    """Índices do cardápio ordenado (category, name) — igual ao bot."""

    def _pizza_menu(self):
        return list(
            Product.objects.filter(category__in=['PIZZA', 'PIZZA_DOCE'], active=True)
            .order_by('category', 'name')
        )

    def _pizza_index(self, name: str) -> int:
        for i, p in enumerate(self._pizza_menu(), 1):
            if p.name == name:
                return i
        raise ValueError(f'Pizza não encontrada: {name}')

    def _setup_promo_half_or_full(self, pizza1_name='Calabresa', pizza2_name='Mussarela'):
        p1 = self.products[pizza1_name]
        p2 = self.products[pizza2_name]
        set_conversation_state(self.PHONE, 'awaiting_promo_half_or_full', {
            'promo': True,
            'pizza1_id': p1.id,
            'pizza2_id': p2.id,
            'pizza1_name': p1.name,
            'pizza2_name': p2.name,
            'existing_items': [],
            'order_type': 'DELIVERY',
        })


class PromoFlowTests(PromoCatalogMixin, BotTestCase):
    def test_inicia_promo(self):
        msg = handle_promo_order(self.PHONE)
        self.assertIn('R$ 55', msg)
        self.assertEqual(get_conversation_state(self.PHONE)['state'], 'awaiting_promo_pizza_1')

    def test_dois_numeros_vai_para_meio_ou_inteiras(self):
        handle_promo_order(self.PHONE)
        idx1 = self._pizza_index('Calabresa')
        idx2 = self._pizza_index('Mussarela')
        msg = handle_promo_pizza_1(self.PHONE, f'{idx1} e {idx2}')
        self.assertIn('Meio a meio', msg)
        self.assertEqual(get_conversation_state(self.PHONE)['state'], 'awaiting_promo_half_or_full')

    def test_dois_nomes_vai_para_meio_ou_inteiras(self):
        handle_promo_order(self.PHONE)
        msg = handle_promo_pizza_1(self.PHONE, 'calabresa e mussarela')
        self.assertIn('Calabresa', msg)
        self.assertEqual(get_conversation_state(self.PHONE)['state'], 'awaiting_promo_half_or_full')

    def test_duas_inteiras_promo(self):
        self._setup_promo_half_or_full()
        msg = handle_promo_half_or_full(self.PHONE, '2')
        self.assertIn('R$ 55,00', msg)
        state = get_conversation_state(self.PHONE)
        self.assertEqual(state['state'], 'awaiting_promo_more_items')
        self.assertEqual(len(state['data']['items']), 2)
        self.assertEqual(float(state['data']['items'][0]['promo_price']), 27.50)

    def test_meio_a_meio_promo_segunda_pizza(self):
        self._setup_promo_half_or_full()
        handle_promo_half_or_full(self.PHONE, 'meio a meio')
        self.assertEqual(get_conversation_state(self.PHONE)['state'], 'awaiting_promo_second_after_half')

        msg = handle_promo_second_after_half(self.PHONE, 'portuguesa')
        state = get_conversation_state(self.PHONE)
        self.assertEqual(state['state'], 'awaiting_promo_more_items')
        self.assertEqual(len(state['data']['items']), 2)
        self.assertEqual(state['data']['items'][0]['type'], 'half_half')
        self.assertIn('R$ 55,00', msg)

    def test_so_isso_pergunta_entrega_ou_retirada(self):
        self._setup_promo_half_or_full()
        handle_promo_half_or_full(self.PHONE, '2')
        set_conversation_state(self.PHONE, 'awaiting_promo_more_items', {
            **get_conversation_state(self.PHONE)['data'],
            'pizza_1_name': 'Calabresa',
            'pizza_2_name': 'Mussarela',
        })
        msg = handle_promo_more_items(self.PHONE, '3')
        self.assertIn('entrega', msg.lower())
        self.assertEqual(get_conversation_state(self.PHONE)['state'], 'awaiting_promo_order_type')

    def test_retirada_vai_para_bebidas(self):
        items = [
            {'product_id': self.products['Calabresa'].id, 'quantity': 1, 'promo_price': 27.50},
            {'product_id': self.products['Mussarela'].id, 'quantity': 1, 'promo_price': 27.50},
        ]
        set_conversation_state(self.PHONE, 'awaiting_promo_order_type', {'items': items, 'promo': True})
        msg = handle_promo_order_type(self.PHONE, 'retirada')
        self.assertEqual(get_conversation_state(self.PHONE)['state'], 'awaiting_drink_pickup')
        self.assertIn('BEBER', msg.upper())

    @patch('pizzaria.bot_views.send_whatsapp_message')
    def test_promo_e2e_retirada_pix(self, mock_send):
        """Promo inteira → retirada → sem bebida → confirma → escolhe PIX."""
        from pizzaria.bot_views import (
            handle_awaiting_drink_pickup,
            handle_payment_choice,
        )

        handle_promo_order(self.PHONE)
        handle_promo_pizza_1(self.PHONE, 'calabresa e mussarela')
        handle_promo_half_or_full(self.PHONE, '2')
        handle_promo_more_items(self.PHONE, '3')
        handle_promo_order_type(self.PHONE, '2')
        handle_awaiting_drink_pickup(self.PHONE, 'não')
        handle_confirming_pickup(self.PHONE, 'sim')

        state = get_conversation_state(self.PHONE)
        self.assertEqual(state['state'], 'awaiting_payment_choice')
        order_id = state['data']['order_id']

        msg = handle_payment_choice(self.PHONE, 'pix')
        self.assertIn('comprovante', msg.lower())
        self.assertEqual(get_conversation_state(self.PHONE)['state'], 'awaiting_receipt')

        from pizzaria.models import Order
        order = Order.objects.get(id=order_id)
        self.assertEqual(order.order_type, 'PICKUP')
        self.assertEqual(order.items.count(), 2)
        self.assertEqual(order.total, Decimal('55.00'))


class PromoLlmTests(PromoCatalogMixin, BotTestCase):
    @patch('pizzaria.bot_views.send_whatsapp_message')
    def test_process_llm_promo_pairs(self, mock_send):
        resp = process_llm_promo_pairs(
            self.PHONE,
            [['calabresa', 'mussarela']],
            {'is_promo': True},
        )
        self.assertEqual(json.loads(resp.content)['action'], 'promo_pairs_added')
        state = get_conversation_state(self.PHONE)
        self.assertEqual(state['state'], 'awaiting_promo_more_items')
        self.assertEqual(len(state['data']['items']), 2)

    @patch('pizzaria.bot_views.send_whatsapp_message')
    def test_process_llm_promo_items(self, mock_send):
        items = [
            {'name': 'calabresa', 'quantity': 1},
            {'name': 'mussarela', 'quantity': 1},
        ]
        resp = process_llm_promo_items(self.PHONE, items, {'is_promo': True})
        self.assertEqual(json.loads(resp.content)['action'], 'promo_items_added')
        mock_send.assert_called_once()
        sent = mock_send.call_args[0][1]
        self.assertIn('R$ 55.00', sent)

    @patch('pizzaria.bot_views.send_whatsapp_message')
    def test_n8n_envelope_promo_pairs(self, mock_send):
        envelope = {
            'normalized': {'phone': self.PHONE, 'text': 'promo 2 calabresa e mussarela', 'msg_type': 'chat'},
            'buffer': {'combined_text': 'promo 2 calabresa e mussarela'},
            'routing': {'used_llm': True, 'reason': 'test'},
            'llm': {
                'valid': True,
                'result': {
                    'intent': 'order_build',
                    'entities': {
                        'order': {
                            'is_promo': True,
                            'promo_pairs': [['calabresa', 'mussarela']],
                            'items': [],
                        },
                    },
                },
            },
            'address_resolution': None,
        }
        resp = process_n8n_envelope(envelope)
        self.assertEqual(json.loads(resp.content)['action'], 'promo_pairs_added')

    def test_entities_to_draft_promo_retirada(self):
        from pizzaria.bot_views import find_product_fuzzy

        entities = {
            'delivery_type': 'pickup',
            'payment_method': 'pix',
            'order': {
                'is_promo': True,
                'items': [
                    {'name': 'calabresa', 'quantity': 1},
                    {'name': 'mussarela', 'quantity': 1},
                ],
            },
        }
        draft = entities_to_draft(entities, None, find_product_fuzzy)
        self.assertIsNotNone(draft)
        self.assertTrue(draft['is_promo'])
        self.assertEqual(draft['items'][0]['price'], 27.50)
        self.assertEqual(draft['order_type'], 'PICKUP')


class PromoRequestTests(BotTestCase):
    def test_promo_ativa_no_texto(self):
        self.settings.promo_active = True
        self.settings.promo_text = '2 por 55'
        self.settings.save()
        msg = handle_promo_request(self.PHONE)
        self.assertIn('R$ 55,00', msg)

    def test_promo_inativa(self):
        self.settings.promo_active = False
        self.settings.save()
        msg = handle_promo_request(self.PHONE)
        self.assertIn('não temos promoções', msg.lower())
