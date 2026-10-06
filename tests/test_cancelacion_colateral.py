def puede_cancelar_por_usuario(prestamo, usuario_id):
    if usuario_id not in (
        prestamo["solicitante_id"],
        prestamo["tomador_id"]
    ):
        return False

    if prestamo["collateral_txid"]:
        return False

    estados_cancelables = (
        "PUBLICADO",
        "TOMADO_ESPERANDO_MONTO",
        "DEPOSITO_BTC_PENDIENTE",
    )

    return prestamo["estado"] in estados_cancelables


def test_participante_no_puede_cancelar_con_colateral_confirmado():
    prestamo = {
        "solicitante_id": 100,
        "tomador_id": 200,
        "estado": "COLATERAL_CONFIRMADO",
        "collateral_txid": "abc123",
    }

    resultado = puede_cancelar_por_usuario(
        prestamo,
        200
    )

    assert resultado is False


def test_participante_si_puede_cancelar_antes_del_colateral_confirmado():
    prestamo = {
        "solicitante_id": 100,
        "tomador_id": 200,
        "estado": "DEPOSITO_BTC_PENDIENTE",
        "collateral_txid": None,
    }

    resultado = puede_cancelar_por_usuario(
        prestamo,
        200
    )

    assert resultado is True
