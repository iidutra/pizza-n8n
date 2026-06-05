"""Testes de intenções simples, confirmação e mensagens conversacionais."""
from pizzaria.conversational_helpers import (
    build_draft_summary,
    detect_simple_intent,
    entities_to_draft,
    has_order_details,
    is_confirmation,
    is_denial,
    is_help_request,
    is_pure_greeting,
    wants_to_order_vague,
)
from pizzaria.tests.base import BotTestCase


class SimpleIntentTests(BotTestCase):
    """FAQ e saudações — resposta fixa sem LLM."""

    def test_saudacao_pura(self):
        cases = ['oi', 'olá', 'bom dia', 'tudo bem?', 'e aí']
        for text in cases:
            with self.subTest(text=text):
                self.assertEqual(detect_simple_intent(text), 'saudacao')

    def test_saudacao_com_pedido_vago(self):
        cases = [
            'oi tudo bem? queria pedir uma pizza',
            'quero pedir',
            'queria uma pizza',
            'vou fazer um pedido',
        ]
        for text in cases:
            with self.subTest(text=text):
                self.assertEqual(detect_simple_intent(text), 'saudacao_pedido')

    def test_faq_intents(self):
        self.assertEqual(detect_simple_intent('cardápio'), 'cardapio')
        self.assertEqual(detect_simple_intent('ver sabores'), 'cardapio')
        self.assertEqual(detect_simple_intent('que horas abre'), 'horario')
        self.assertEqual(detect_simple_intent('onde fica'), 'localizacao')
        self.assertEqual(detect_simple_intent('aceita pix'), 'pagamento_info')

    def test_repetir_pedido(self):
        for text in ('repetir', 'o de sempre', 'mesmo pedido', 'igual da última'):
            with self.subTest(text=text):
                self.assertEqual(detect_simple_intent(text), 'repetir_pedido')

    def test_pedido_com_detalhes_nao_e_saudacao(self):
        text = '2 calabresa entrega aponia pix'
        self.assertIsNone(detect_simple_intent(text))
        self.assertTrue(has_order_details(text))

    def test_saudacao_com_sabor_vai_para_llm(self):
        self.assertIsNone(detect_simple_intent('oi quero 2 calabresa'))


class ConfirmationTests(BotTestCase):
    def test_confirmacoes(self):
        for word in ('sim', 's', 'ok', 'beleza', 'pode ser', 'sim pode'):
            with self.subTest(word=word):
                self.assertTrue(is_confirmation(word))

    def test_negacoes(self):
        for word in ('não', 'nao', 'mudar', 'errado'):
            with self.subTest(word=word):
                self.assertTrue(is_denial(word))

    def test_ajuda(self):
        self.assertTrue(is_help_request('ajuda'))
        self.assertTrue(is_help_request('não entendi'))


class DraftSummaryTests(BotTestCase):
    def test_resumo_pizza_simples(self):
        draft = {
            'items': [{'name': 'Calabresa', 'quantity': 2, 'price': 40.0}],
            'order_type': 'DELIVERY',
            'address': 'Rua A 10',
            'neighborhood': 'Aponiã',
            'payment_method': 'pix',
            'subtotal': 80.0,
            'delivery_fee': 8.0,
        }
        summary = build_draft_summary(draft)
        self.assertIn('Calabresa', summary)
        self.assertIn('R$ 88.00', summary)
        self.assertIn('SIM', summary)

    def test_resumo_meio_a_meio(self):
        draft = {
            'items': [{
                'type': 'half_half',
                'name': '½ Calabresa + ½ Frango com Catupiry',
                'quantity': 1,
                'price': 42.0,
            }],
            'order_type': 'PICKUP',
            'payment_method': 'cash',
            'subtotal': 42.0,
            'delivery_fee': 0,
        }
        summary = build_draft_summary(draft)
        self.assertIn('½ Calabresa', summary)
        self.assertIn('Retirada', summary)


class EntitiesToDraftTests(BotTestCase):
    def test_pedido_completo_llm(self):
        from pizzaria.bot_views import find_product_fuzzy

        entities = {
            'delivery_type': 'delivery',
            'payment_method': 'pix',
            'address': {'address_line': 'Rua Teste', 'number': '100'},
            'order': {
                'items': [{'name': 'calabresa', 'quantity': 2}],
            },
        }
        resolution = {
            'status': 'matched',
            'matched_neighborhood': 'Aponiã',
            'delivery_fee': 8.0,
        }
        draft = entities_to_draft(entities, resolution, find_product_fuzzy)
        self.assertIsNotNone(draft)
        self.assertEqual(len(draft['items']), 1)
        self.assertEqual(draft['items'][0]['quantity'], 2)
        self.assertEqual(draft['payment_method'], 'pix')
        self.assertEqual(draft['delivery_fee'], 8.0)

    def test_pedido_incompleto_retorna_none(self):
        from pizzaria.bot_views import find_product_fuzzy

        entities = {
            'delivery_type': 'unknown',
            'payment_method': 'unknown',
            'order': {'items': [{'name': 'calabresa', 'quantity': 1}]},
        }
        self.assertIsNone(entities_to_draft(entities, None, find_product_fuzzy))

    def test_meio_a_meio_llm(self):
        from pizzaria.bot_views import find_product_fuzzy

        entities = {
            'delivery_type': 'pickup',
            'payment_method': 'pix',
            'order': {
                'items': [{
                    'is_half_half': True,
                    'half_flavors': ['calabresa', 'frango'],
                    'quantity': 1,
                }],
            },
        }
        draft = entities_to_draft(entities, None, find_product_fuzzy)
        self.assertIsNotNone(draft)
        self.assertEqual(draft['items'][0]['type'], 'half_half')
