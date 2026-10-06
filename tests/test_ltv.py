import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from gestion_ltv import (
    calcular_ltv,
    obtener_estado_ltv,
    evaluar_prestamo,
    gracia_terminada,
    iniciar_gracia,
)


def test_deposito_con_ltv_normal_no_debe_iniciar_gracia():
    monto_prestamo = 1_000_000
    valor_colateral = 2_000_000

    ltv = calcular_ltv(
        monto_prestamo,
        valor_colateral
    )

    assert ltv == 50.0
    assert obtener_estado_ltv(ltv) == "NORMAL"

    resultado = evaluar_prestamo(
        ltv=ltv,
        estado_actual="COLATERAL_CONFIRMADO",
    )

    assert resultado["accion"] == "ACTUALIZAR_LTV"
    assert resultado["estado"] == "NORMAL"


def test_ltv_84_no_debe_iniciar_gracia():
    resultado = evaluar_prestamo(
        ltv=84.0,
        estado_actual="COLATERAL_CONFIRMADO",
    )

    assert resultado["accion"] == "ACTUALIZAR_LTV"
    assert resultado["estado"] == "CRITICO"


def test_ltv_85_debe_iniciar_gracia_y_no_liquidar():
    resultado = evaluar_prestamo(
        ltv=85.0,
        estado_actual="COLATERAL_CONFIRMADO",
    )

    assert resultado["accion"] == "INICIAR_GRACIA"
    assert resultado["estado"] == "GRACIA"


def test_ltv_50_nunca_debe_ser_liquidado():
    resultado = evaluar_prestamo(
        ltv=50.0,
        estado_actual="COLATERAL_CONFIRMADO",
    )

    assert resultado["accion"] != "LIQUIDAR"
    assert resultado["estado"] != "LIQUIDADA"


def test_si_el_precio_se_recupera_durante_gracia_no_debe_liquidar():
    resultado = evaluar_prestamo(
        70.0,
        "GRACIA",
        None
    )

    assert resultado["accion"] == "CANCELAR_GRACIA"
    assert resultado["estado"] == "VIGILANCIA"


def test_recuperacion_cancela_gracia_y_no_puede_liquidar_por_gracia_vieja():
    resultado_recuperacion = evaluar_prestamo(
        70.0,
        "GRACIA",
        None
    )

    assert resultado_recuperacion["accion"] == "CANCELAR_GRACIA"
    assert resultado_recuperacion["estado"] == "VIGILANCIA"

    resultado_despues = evaluar_prestamo(
        70.0,
        resultado_recuperacion["estado"],
        None
    )

    assert resultado_despues["accion"] == "ACTUALIZAR_LTV"
    assert resultado_despues["estado"] == "VIGILANCIA"




def test_gracia_vieja_no_liquida_despues_de_recuperacion():
    inicio, fin = iniciar_gracia()

    # BTC se recupera mientras estaba en gracia.
    recuperacion = evaluar_prestamo(
        ltv=70.0,
        estado_actual="GRACIA",
        gracia_fin=fin,
    )

    assert recuperacion["accion"] == "CANCELAR_GRACIA"
    assert recuperacion["estado"] == "VIGILANCIA"

    # La gracia quedó cancelada.
    # Aunque pase la fecha de la gracia antigua,
    # no debe existir una gracia activa que pueda liquidar.
    resultado_final = evaluar_prestamo(
        ltv=70.0,
        estado_actual=recuperacion["estado"],
        gracia_fin=None,
    )

    assert resultado_final["accion"] == "ACTUALIZAR_LTV"
    assert resultado_final["estado"] == "VIGILANCIA"
    assert resultado_final["accion"] != "LIQUIDAR"
    assert resultado_final["estado"] != "LIQUIDADA"
