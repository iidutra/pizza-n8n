"""Testes de parsers: meio a meio, múltiplas pizzas, pagamento, bairro."""
from decimal import Decimal

from pizzaria.bot_views import (
    find_product_fuzzy,
    is_cancel_command,
    is_greeting,
    is_half_half_request,
    parse_half_half,
    parse_multiple_half_half_orders,
    parse_multiple_pizzas,
)
from pizzaria.order_coverage import (
    fill_partial_field,
    get_missing_fields,
    match_neighborhood_in_text,
    parse_llm_item_to_cart,
    parse_order_type_from_text,
    parse_payment_from_text,
)
from pizzaria.tests.base import BotTestCase


class HalfHalfParserTests(BotTestCase):
    """Meio a meio — casos falados pelo cliente."""

    def test_detecta_meio_a_meio(self):
        phrases = [
            'calabresa com metade de frango',
            'meio calabresa meio frango',
            '1 calabresa e bacon',
        ]
        for p in phrases:
            with self.subTest(p=p):
                self.assertTrue(is_half_half_request(p))

    def test_parse_simples(self):
        s1, s2 = parse_half_half('calabresa com metade de frango')
        self.assertEqual(s1, 'calabresa')
        self.assertEqual(s2, 'frango')

    def test_parse_meio_meio_explicito(self):
        s1, s2 = parse_half_half('meio calabresa meio baiana')
        self.assertEqual(s1, 'calabresa')
        self.assertEqual(s2, 'baiana')

    def test_multiplas_meio_a_meio_outra(self):
        msg = 'queria 1 calabresa com metade de frango e outra de queijo com bolonhesa'
        pairs = parse_multiple_half_half_orders(msg)
        self.assertEqual(len(pairs), 2)
        self.assertEqual(pairs[0], ('calabresa', 'frango'))
        self.assertEqual(pairs[1], ('queijo', 'bolonhesa'))

    def test_multiplas_com_metade_nas_duas(self):
        msg = 'calabresa com metade frango e outra queijo com metade portuguesa'
        pairs = parse_multiple_half_half_orders(msg)
        self.assertEqual(len(pairs), 2)
        self.assertEqual(pairs[0][0], 'calabresa')
        self.assertEqual(pairs[1][1], 'portuguesa')

    def test_uma_meio_a_meio_apenas(self):
        pairs = parse_multiple_half_half_orders('calabresa com metade de frango')
        self.assertEqual(len(pairs), 1)
        self.assertEqual(pairs[0], ('calabresa', 'frango'))


class ProductFuzzyTests(BotTestCase):
    """Sinônimos e busca de produtos."""

    def test_sinonimos(self):
        cases = {
            'frango': 'Frango com Catupiry',
            'queijo': '4 Queijos',
            'bolonhesa': 'Portuguesa',
            'calabresa': 'Calabresa',
            '4 queijos': '4 Queijos',
        }
        for query, expected in cases.items():
            with self.subTest(query=query):
                product = find_product_fuzzy(query)
                self.assertIsNotNone(product, f'Não encontrou: {query}')
                self.assertEqual(product.name, expected)

    def test_por_numero(self):
        product = find_product_fuzzy('1')
        self.assertIsNotNone(product)

    def test_multiplas_pizzas_por_nome(self):
        result = parse_multiple_pizzas('2 portuguesa e 1 calabresa')
        self.assertIsNotNone(result)
        self.assertEqual(len(result), 2)
        names = {r['product'].name for r in result}
        self.assertIn('Portuguesa', names)
        self.assertIn('Calabresa', names)


class PaymentAndOrderTypeTests(BotTestCase):
    def test_pagamento(self):
        self.assertEqual(parse_payment_from_text('pix'), 'pix')
        self.assertEqual(parse_payment_from_text('dinheiro'), 'cash')
        self.assertEqual(parse_payment_from_text('cartão'), 'credit')
        self.assertEqual(parse_payment_from_text('vou pagar no pix'), 'pix')

    def test_tipo_pedido(self):
        self.assertEqual(parse_order_type_from_text('entrega'), 'DELIVERY')
        self.assertEqual(parse_order_type_from_text('retirada'), 'PICKUP')
        self.assertIsNone(parse_order_type_from_text('calabresa'))


class NeighborhoodTests(BotTestCase):
    def test_match_bairro(self):
        neighborhood, fee = match_neighborhood_in_text('rua tal 123 aponia')
        self.assertEqual(neighborhood, 'Aponiã')
        self.assertEqual(fee, 8.0)

    def test_bairro_nao_encontrado(self):
        neighborhood, fee = match_neighborhood_in_text('rua xyz 999')
        self.assertIsNone(neighborhood)


class PartialDraftTests(BotTestCase):
    def test_campos_faltando_entrega(self):
        partial = {
            'items': [{'name': 'Calabresa', 'quantity': 1, 'price': 40.0}],
            'order_type': 'unknown',
            'payment_method': 'unknown',
        }
        missing = get_missing_fields(partial)
        self.assertIn('order_type', missing)
        self.assertIn('payment', missing)

    def test_preenche_pagamento(self):
        partial = {
            'items': [{'name': 'Calabresa', 'quantity': 1, 'price': 40.0}],
            'order_type': 'DELIVERY',
            'payment_method': 'unknown',
            'address': 'Rua A 1 aponia',
            'neighborhood': 'Aponiã',
            'delivery_fee': 8.0,
        }
        updated = fill_partial_field(partial, 'payment', 'pix', find_product_fuzzy)
        self.assertEqual(updated['payment_method'], 'pix')

    def test_preenche_retirada(self):
        partial = {
            'items': [{'name': 'Calabresa', 'quantity': 1, 'price': 40.0}],
            'order_type': 'unknown',
            'payment_method': 'unknown',
        }
        updated = fill_partial_field(partial, 'order_type', 'retirada', find_product_fuzzy)
        self.assertEqual(updated['order_type'], 'PICKUP')
        self.assertIsNone(updated['address'])


class LlmItemParserTests(BotTestCase):
    def test_item_simples(self):
        item = parse_llm_item_to_cart(
            {'name': 'calabresa', 'quantity': 2},
            find_product_fuzzy,
        )
        self.assertEqual(item['name'], 'Calabresa')
        self.assertEqual(item['quantity'], 2)

    def test_item_meio_a_meio(self):
        item = parse_llm_item_to_cart(
            {'is_half_half': True, 'half_flavors': ['calabresa', 'frango'], 'quantity': 1},
            find_product_fuzzy,
        )
        self.assertEqual(item['type'], 'half_half')
        self.assertIn('½ Calabresa', item['name'])
        self.assertEqual(item['price'], 42.0)

    def test_preco_promo(self):
        item = parse_llm_item_to_cart(
            {'name': 'calabresa', 'quantity': 1},
            find_product_fuzzy,
            is_promo=True,
        )
        self.assertEqual(item['price'], 27.50)


class CommandDetectionTests(BotTestCase):
    def test_cancelamento(self):
        self.assertTrue(is_cancel_command('cancelar'))
        self.assertTrue(is_cancel_command('desistir'))

    def test_saudacao_no_fluxo(self):
        self.assertTrue(is_greeting('oi'))
        self.assertTrue(is_greeting('bom dia'))
