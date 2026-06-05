"""Adiciona detecção de intenções simples no router n8n (FAQ + saudação, sem LLM)."""
import json
from pathlib import Path

WORKFLOW_PATH = Path(__file__).resolve().parent.parent / 'n8n_workflow_hybrid_bot.json'

DETECT_FN = """
function detectSimpleIntent(t) {
  if (/cardápio|cardapio|menu|sabores|o que tem|ver pizza|ver o card/i.test(t)) return 'cardapio';
  if (/horário|horario|que horas|abre|fecha|funciona|tá aberto|ta aberto|esta aberto|está aberto|vocês abrem|voces abrem/i.test(t)) return 'horario';
  if (/onde fica|localização|localizacao|endereço da|endereco da|como chegar|fica onde/i.test(t)) return 'localizacao';
  if (/formas de pagamento|como paga|como posso pagar|aceita pix|aceita cartão|aceita cartao|aceita dinheiro/i.test(t)) return 'pagamento_info';

  const wantsOrder = /quer(o|ia) pedir|fazer pedido|quero (uma )?pizza|queria (uma )?pizza|vou pedir|pedir (uma )?pizza/i.test(t)
    || (/pizza/i.test(t) && /quero|queria|pedir|pedido|vou/i.test(t));
  const hasDetails = /calabresa|mussarela|frango|queijo|portuguesa|bacon|pix|dinheiro|cartao|cartão|entrega|retirada|rua|avenida|bairro|\\d{3,5}/i.test(t);
  const hasGreeting = /\\b(oi|ola|olá|bom dia|boa tarde|boa noite|tudo bem|como vai|eae|opa|beleza)\\b/i.test(t);

  if (wantsOrder && !hasDetails) return 'saudacao_pedido';
  if (hasGreeting && !hasDetails && t.split(/\\s+/).length <= 12) return 'saudacao';
  return null;
}
"""


def main():
    workflow = json.loads(WORKFLOW_PATH.read_text(encoding='utf-8'))
    for node in workflow['nodes']:
        if node.get('name') != 'Router Rules-First':
            continue
        code = node['parameters']['jsCode']
        if 'detectSimpleIntent' in code:
            print('Router já possui detectSimpleIntent')
            return

        anchor = 'const isSafePattern = SAFE_PATTERNS.some(pattern => pattern.test(text));'
        if anchor not in code:
            raise RuntimeError('Router anchor not found')

        code = code.replace(
            anchor,
            DETECT_FN + '\n' + anchor + '\n\nconst simpleIntent = detectSimpleIntent(text);',
            1,
        )
        code = code.replace(
            'let needsLLM = !isSafePattern && (',
            'let needsLLM = !simpleIntent && !isSafePattern && (',
            1,
        )
        code = code.replace(
            'if (data.normalized?.was_audio && text.length > 1) {\n  needsLLM = true;\n}',
            'if (!simpleIntent && data.normalized?.was_audio && text.length > 1) {\n  needsLLM = true;\n}',
            1,
        )
        code = code.replace(
            "let reason = 'safe_pattern';\nif (needsLLM) {",
            "let reason = 'safe_pattern';\nif (simpleIntent) reason = 'simple_' + simpleIntent;\nelse if (needsLLM) {",
            1,
        )
        code = code.replace(
            '      used_llm: needsLLM,\n      reason: reason,',
            '      used_llm: needsLLM,\n      simple_intent: simpleIntent,\n      reason: reason,',
            1,
        )
        node['parameters']['jsCode'] = code
        break
    else:
        raise RuntimeError('Router Rules-First node not found')

    WORKFLOW_PATH.write_text(json.dumps(workflow, indent=2, ensure_ascii=False), encoding='utf-8')
    print(f'Router atualizado: {WORKFLOW_PATH}')


if __name__ == '__main__':
    main()
