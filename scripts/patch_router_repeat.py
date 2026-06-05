"""Adiciona repetir_pedido ao router n8n."""
import json
from pathlib import Path

WORKFLOW_PATH = Path(__file__).resolve().parent.parent / 'n8n_workflow_hybrid_bot.json'

OLD = "  if (wantsOrder && !hasDetails) return 'saudacao_pedido';"
NEW = (
    "  if (/repetir|de novo|mesmo pedido|ultimo pedido|o de sempre|igual da/i.test(t)) return 'repetir_pedido';\n"
    "  if (wantsOrder && !hasDetails) return 'saudacao_pedido';"
)


def main():
    workflow = json.loads(WORKFLOW_PATH.read_text(encoding='utf-8'))
    for node in workflow['nodes']:
        if node.get('name') != 'Router Rules-First':
            continue
        code = node['parameters']['jsCode']
        if 'repetir_pedido' in code:
            print('Já possui repetir_pedido')
            return
        if OLD not in code:
            raise RuntimeError('Anchor not found')
        node['parameters']['jsCode'] = code.replace(OLD, NEW, 1)
        break
    WORKFLOW_PATH.write_text(json.dumps(workflow, indent=2, ensure_ascii=False), encoding='utf-8')
    print('Router atualizado')


if __name__ == '__main__':
    main()
