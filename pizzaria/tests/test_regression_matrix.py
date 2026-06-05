"""Matriz de cenários cobertos pela suite regressiva."""
from django.test import SimpleTestCase


class RegressionMatrixTests(SimpleTestCase):
    """
    Documentação viva: cada cenário abaixo tem teste correspondente.
    Se adicionar fluxo novo, inclua aqui e crie o teste.
    """

    SCENARIOS = {
        'saudacao': 'Oi / bom dia → resposta calorosa sem LLM',
        'saudacao_pedido': 'Oi quero pedir pizza → orientação sem LLM',
        'faq_cardapio': 'cardápio / sabores',
        'faq_horario': 'que horas abre',
        'faq_localizacao': 'onde fica',
        'faq_pagamento': 'aceita pix',
        'repetir_pedido': 'repetir / o de sempre → último pedido',
        'repetir_sem_historico': 'repetir sem pedido anterior',
        'meio_a_meio_simples': 'calabresa com metade frango',
        'meio_a_meio_multi': 'calabresa metade frango e outra queijo com bolonhesa',
        'sinonimos': 'frango→catupiry, queijo→4 queijos, bolonhesa→portuguesa',
        'multiplas_pizzas': '2 portuguesa e 1 calabresa',
        'pedido_parcial': 'só sabor → pergunta entrega/retirada/pagamento',
        'pedido_completo_llm': 'sabor + retirada + pix → rascunho SIM',
        'confirmacao_sim': 'SIM → cria pedido no banco',
        'confirmacao_mudar': 'mudar → volta ao welcome',
        'n8n_fallback_meio_meio': 'LLM falhou + texto meio a meio → parser local',
        'n8n_estado_prioritario': 'awaiting_address ignora LLM',
        'bairro_fuzzy': 'aponia → Aponiã + taxa',
        'pagamento_texto': 'pix / dinheiro / cartão',
        'confusao': '2+ erros → should_simplify',
        'validacao_phone': 'telefone WhatsApp válido',
        'promo_inicio': 'promo → escolha 2 sabores',
        'promo_duas_inteiras': 'promo meio ou inteiras → 2 inteiras R$55',
        'promo_meio_a_meio': 'promo meio a meio + 2ª pizza',
        'promo_e2e_retirada': 'promo completa → retirada → PIX',
        'promo_llm_pairs': 'LLM promo_pairs → carrinho promo',
        'promo_llm_items': 'LLM items promo → par R$55',
        'pix_escolha': 'escolhe PIX → chave + aguarda foto',
        'pix_comprovante': 'foto comprovante → RECEIPT_RECEIVED',
        'pix_pagar_entrega': 'sem foto → pagar na entrega',
        'pix_e2e_draft': 'rascunho SIM → PIX → comprovante PDF',
    }

    def test_matriz_tem_cenarios_minimos(self):
        required = {
            'meio_a_meio_multi', 'repetir_pedido', 'pedido_parcial',
            'confirmacao_sim', 'n8n_fallback_meio_meio',
            'promo_e2e_retirada', 'pix_comprovante', 'pix_e2e_draft',
        }
        self.assertTrue(required.issubset(set(self.SCENARIOS.keys())))

    def test_total_cenarios_documentados(self):
        self.assertGreaterEqual(len(self.SCENARIOS), 30)
