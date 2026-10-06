LTV_MAXIMO = 85.0


def evaluar_bloque(ltv):
    if ltv < LTV_MAXIMO:
        return "LTV_NORMAL"
    else:
        return "LTV_EN_O_SOBRE_EL_LIMITE"


def test_ltv_normal_deberia_entrar_en_normal():
    ltv = 50.0

    resultado = evaluar_bloque(ltv)

    assert resultado == "LTV_NORMAL"


def test_ltv_85_deberia_entrar_en_limite():
    ltv = 85.0

    resultado = evaluar_bloque(ltv)

    assert resultado == "LTV_EN_O_SOBRE_EL_LIMITE"
