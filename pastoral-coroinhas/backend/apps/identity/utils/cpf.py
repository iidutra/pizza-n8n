import re


def normalizar_cpf(cpf: str) -> str:
    return re.sub(r"\D", "", cpf or "")


def validar_cpf(cpf: str) -> bool:
    cpf = normalizar_cpf(cpf)
    if len(cpf) != 11 or cpf == cpf[0] * 11:
        return False

    def calcular_digito(base: str, peso_inicial: int) -> int:
        soma = sum(int(d) * p for d, p in zip(base, range(peso_inicial, 1, -1)))
        resto = soma % 11
        return 0 if resto < 2 else 11 - resto

    d1 = calcular_digito(cpf[:9], 10)
    d2 = calcular_digito(cpf[:10], 11)
    return cpf[-2:] == f"{d1}{d2}"


def mascarar_cpf(cpf: str) -> str:
    cpf = normalizar_cpf(cpf)
    if len(cpf) != 11:
        return cpf
    return f"***.{cpf[3:6]}.{cpf[6:9]}-**"


def senha_inicial_cpf(cpf: str) -> str:
    return normalizar_cpf(cpf)[-4:]
