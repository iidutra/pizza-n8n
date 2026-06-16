from apps.identity.utils.cpf import normalizar_cpf, validar_cpf
from apps.scheduling.models import FuncaoEscala


def test_normalizar_cpf():
    assert normalizar_cpf("111.444.777-35") == "11144477735"


def test_validar_cpf_valido():
    assert validar_cpf("11144477735") is True
    assert validar_cpf("52998224725") is True


def test_validar_cpf_invalido():
    assert validar_cpf("11111111111") is False
    assert validar_cpf("123") is False


def test_funcoes_escala_tem_duas_velas():
    valores = [c.value for c in FuncaoEscala]
    assert "Vela1" in valores
    assert "Vela2" in valores
    assert "Velas" not in valores
