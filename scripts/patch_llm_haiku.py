"""Troca LLM do workflow n8n de Groq Llama para Anthropic Claude Haiku."""
import json
import re
from pathlib import Path

WORKFLOW_PATH = Path(__file__).resolve().parent.parent / 'n8n_workflow_hybrid_bot.json'
MODEL = 'claude-haiku-4-5'
PROVIDER = 'anthropic'


def extract_system_prompt(json_body: str) -> str:
    match = re.search(
        r'"role": "system",\s*"content": "(.+?)"\s*\n\s*},\s*\n\s*{\s*\n\s*"role": "user"',
        json_body,
        re.DOTALL,
    )
    if not match:
        raise RuntimeError('System prompt not found in Chamar Groq jsonBody')
    return match.group(1)


def build_anthropic_body(system_prompt: str) -> str:
    user_content = (
        'BAIRROS CADASTRADOS: {{ $json.llm_context.neighborhoods }}\\n\\n'
        'CARDÁPIO: {{ $json.llm_context.products }}\\n\\n'
        'MENSAGEM DO CLIENTE: \\"{{ $json.llm_context.text }}\\"'
    )
    return (
        '={\n'
        f'  "model": "{MODEL}",\n'
        '  "max_tokens": 2048,\n'
        '  "temperature": 0.1,\n'
        f'  "system": "{system_prompt}",\n'
        '  "messages": [\n'
        '    {\n'
        '      "role": "user",\n'
        f'      "content": "{user_content}"\n'
        '    }\n'
        '  ]\n'
        '}'
    )


PARSE_LLM_SUFFIX = """  const content =
    llmResponse.content?.[0]?.text ||
    llmResponse.choices?.[0]?.message?.content ||
    '';"""


def patch_parse_node(code: str) -> str:
    old = "  const content = llmResponse.choices?.[0]?.message?.content || '';"
    if old not in code:
        if 'llmResponse.content?.[0]?.text' in code:
            return code
        raise RuntimeError('Parse node content line not found')
    code = code.replace(old, PARSE_LLM_SUFFIX.strip())
    code = code.replace("provider: 'groq'", f"provider: '{PROVIDER}'")
    code = code.replace("model: 'llama-3.3-70b-versatile'", f"model: '{MODEL}'")
    return code


def main():
    workflow = json.loads(WORKFLOW_PATH.read_text(encoding='utf-8'))
    old_name = 'Chamar Groq'
    new_name = 'Chamar Claude Haiku'

    for node in workflow['nodes']:
        if node.get('name') == old_name:
            system_prompt = extract_system_prompt(node['parameters']['jsonBody'])
            node['name'] = new_name
            node['id'] = 'http-llm-anthropic'
            node['parameters']['url'] = 'https://api.anthropic.com/v1/messages'
            node['parameters']['headerParameters'] = {
                'parameters': [
                    {
                        'name': 'x-api-key',
                        'value': '={{ $env.ANTHROPIC_API_KEY }}',
                    },
                    {
                        'name': 'anthropic-version',
                        'value': '2023-06-01',
                    },
                    {
                        'name': 'Content-Type',
                        'value': 'application/json',
                    },
                ]
            }
            node['parameters']['jsonBody'] = build_anthropic_body(system_prompt)
        elif node.get('name') == 'Parse LLM Response':
            node['parameters']['jsCode'] = patch_parse_node(node['parameters']['jsCode'])

    connections = workflow['connections']
    if old_name in connections:
        connections[new_name] = connections.pop(old_name)
    for conn in connections.values():
        for outputs in conn.get('main', []):
            for link in outputs:
                if link.get('node') == old_name:
                    link['node'] = new_name

    WORKFLOW_PATH.write_text(
        json.dumps(workflow, indent=2, ensure_ascii=False),
        encoding='utf-8',
    )
    print(f'Workflow atualizado para {MODEL}: {WORKFLOW_PATH}')


if __name__ == '__main__':
    main()
