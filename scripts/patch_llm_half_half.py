"""Adiciona regras de meio a meio multi-pizza ao prompt LLM."""
import json
from pathlib import Path

WORKFLOW_PATH = Path(__file__).resolve().parent.parent / 'n8n_workflow_hybrid_bot.json'

RULE = (
    "\\n14. Meio a meio: 'com metade de', 'meio X meio Y' → is_half_half=true, "
    "half_flavors=[sabor1,sabor2]. 'e outra' = pizza separada (novo item). "
    "Ex: 'calabresa com metade frango e outra queijo com bolonhesa' → 2 items meio a meio"
)


def main():
    workflow = json.loads(WORKFLOW_PATH.read_text(encoding='utf-8'))
    for node in workflow['nodes']:
        if node.get('name') != 'Chamar Claude Haiku':
            continue
        body = node['parameters']['jsonBody']
        if '14. Meio a meio' in body:
            print('Regra 14 já existe')
            return
        anchor = '13. Saudação + conversa'
        if anchor not in body:
            anchor = '10. Se pedir múltiplas pizzas'
        body = body.replace(anchor, RULE + '\\n' + anchor, 1)
        body = body.replace(
            '\\"is_half_half\\": false,',
            '\\"is_half_half\\": false,\\n      \\"half_flavors\\": [],',
            1,
        )
        node['parameters']['jsonBody'] = body
        break
    WORKFLOW_PATH.write_text(json.dumps(workflow, indent=2, ensure_ascii=False), encoding='utf-8')
    print('LLM prompt atualizado')


if __name__ == '__main__':
    main()
