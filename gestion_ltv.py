
from datetime import datetime, timedelta


# ============================================================
# CONFIGURACIÓN DEL LTV
# ============================================================

LTV_MAXIMO = 85.0

# Periodo de gracia cuando el LTV llega al máximo
HORAS_GRACIA = 24


# ============================================================
# CALCULAR LTV
# ============================================================

def calcular_ltv(monto_prestamo, valor_colateral):
    """
    LTV = valor del préstamo / valor del colateral * 100
    """

    if valor_colateral <= 0:
        raise ValueError("El valor del colateral debe ser mayor que cero.")

    return (monto_prestamo / valor_colateral) * 100


# ============================================================
# DETERMINAR ESTADO DEL LTV
# ============================================================

def obtener_estado_ltv(ltv):
    """
    Determina el nivel de riesgo según el LTV.
    """

    if ltv >= LTV_MAXIMO:
        return "GRACIA"

    if ltv >= 80:
        return "CRITICO"

    if ltv >= 75:
        return "ALERTA"

    if ltv >= 70:
        return "VIGILANCIA"

    return "NORMAL"


# ============================================================
# INICIAR PERIODO DE GRACIA
# ============================================================

def iniciar_gracia():
    """
    Devuelve inicio y final del periodo de gracia.
    """

    ahora = datetime.utcnow()

    inicio = ahora
    fin = ahora + timedelta(hours=HORAS_GRACIA)

    return inicio, fin


# ============================================================
# COMPROBAR SI LA GRACIA TERMINÓ
# ============================================================

def gracia_terminada(gracia_fin):
    """
    Comprueba si ya terminó el periodo de gracia.
    """

    if not gracia_fin:
        return False

    ahora = datetime.utcnow()

    return ahora >= gracia_fin


# ============================================================
# DECIDIR QUÉ HACER CON EL PRÉSTAMO
# ============================================================

def evaluar_prestamo(
    ltv,
    estado_actual,
    gracia_fin=None
):
    """
    Decide el siguiente estado del préstamo.

    No modifica la base de datos.
    Solamente devuelve la decisión.
    """

    # --------------------------------------------------------
    # Si ya está liquidado, no hacer nada
    # --------------------------------------------------------

    if estado_actual == "LIQUIDADA":
        return {
            "accion": "NINGUNA",
            "estado": "LIQUIDADA"
        }

    # --------------------------------------------------------
    # LTV todavía por debajo del máximo
    # --------------------------------------------------------

    if ltv < LTV_MAXIMO:

        # Si estaba en gracia y recuperó el LTV
        if estado_actual == "GRACIA":

            return {
                "accion": "CANCELAR_GRACIA",
                "estado": obtener_estado_ltv(ltv)
            }

        return {
            "accion": "ACTUALIZAR_LTV",
            "estado": obtener_estado_ltv(ltv)
        }

    # --------------------------------------------------------
    # LTV >= 85%
    # --------------------------------------------------------

    if estado_actual != "GRACIA":

        inicio, fin = iniciar_gracia()

        return {
            "accion": "INICIAR_GRACIA",
            "estado": "GRACIA",
            "gracia_inicio": inicio,
            "gracia_fin": fin
        }

    # --------------------------------------------------------
    # Ya estaba en gracia
    # --------------------------------------------------------

    if gracia_terminada(gracia_fin):

        return {
            "accion": "LIQUIDAR",
            "estado": "LIQUIDADA"
        }

    # --------------------------------------------------------
    # Todavía continúa la gracia
    # --------------------------------------------------------

    return {
        "accion": "CONTINUAR_GRACIA",
        "estado": "GRACIA"
    }


# ============================================================
# MENSAJES
# ============================================================

def mensaje_ltv(public_id, ltv):

    estado = obtener_estado_ltv(ltv)

    if estado == "NORMAL":
        icono = "🟢"
        texto = "El préstamo se encuentra en condiciones normales."

    elif estado == "VIGILANCIA":
        icono = "🟡"
        texto = "El LTV está aumentando. Se recomienda vigilar la operación."

    elif estado == "ALERTA":
        icono = "🟠"
        texto = "El LTV continúa aumentando y se acerca al límite."

    elif estado == "CRITICO":
        icono = "🔴"
        texto = "El LTV está muy cerca del límite máximo."

    else:
        icono = "⏳"
        texto = "Se ha iniciado el periodo de gracia."

    return (
        f"{icono} ACTUALIZACIÓN LTV\n\n"
        f"🆔 Contrato:\n"
        f"{public_id}\n\n"
        f"📊 LTV actual: {ltv:.2f}%\n"
        f"🎯 LTV máximo: {LTV_MAXIMO:.2f}%\n\n"
        f"{texto}"
    )


def mensaje_inicio_gracia(public_id, ltv):

    return (
        "🚨 LTV MÁXIMO ALCANZADO\n\n"
        f"🆔 Contrato:\n"
        f"{public_id}\n\n"
        f"📊 LTV actual: {ltv:.2f}%\n"
        f"🎯 Límite: {LTV_MAXIMO:.2f}%\n\n"
        f"⏳ PERIODO DE GRACIA INICIADO\n\n"
        f"El periodo de gracia es de {HORAS_GRACIA} horas.\n\n"
        "Durante este periodo el LTV continuará siendo monitoreado.\n"
        "Si el LTV vuelve a estar por debajo del límite, "
        "la operación podrá volver a estado normal."
    )


def mensaje_liquidacion(public_id, ltv):

    return (
        "🔴 ORDEN LIQUIDADA\n\n"
        f"🆔 Contrato:\n"
        f"{public_id}\n\n"
        f"📊 LTV final: {ltv:.2f}%\n"
        f"🎯 Límite: {LTV_MAXIMO:.2f}%\n\n"
        "⏰ El periodo de gracia ha terminado.\n\n"
        "La operación ha pasado a estado LIQUIDADA.\n\n"
        "El proceso de recuperación de los fondos "
        "puede continuar mediante la transacción de liquidación "
        "correspondiente."
    )
if __name__ == "__main__":

    monto = 1_000_000

    valores_colateral = [
        1_500_000,
        1_250_000,
        1_200_000,
        1_176_471,
        1_100_000,
    ]

    for valor in valores_colateral:

        ltv = calcular_ltv(
            monto,
            valor
        )

        estado = obtener_estado_ltv(ltv)

        print(
            f"Colateral: {valor:,.0f} COP | "
            f"LTV: {ltv:.2f}% | "
            f"Estado: {estado}"
        )