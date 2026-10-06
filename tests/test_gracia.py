from datetime import datetime, timedelta


DIAS_GRACIA = 4


def calcular_fin_gracia(ahora):
    return ahora + timedelta(days=DIAS_GRACIA)


def test_periodo_gracia_es_de_4_dias():
    inicio = datetime(2026, 10, 6, 10, 0, 0)

    fin = calcular_fin_gracia(inicio)

    assert fin - inicio == timedelta(days=4)


def test_no_debe_terminar_antes_de_4_dias():
    inicio = datetime(2026, 10, 6, 10, 0, 0)

    fin = calcular_fin_gracia(inicio)

    momento_antes = inicio + timedelta(days=3, hours=23, minutes=59)

    assert momento_antes < fin


def test_debe_terminar_exactamente_a_los_4_dias():
    inicio = datetime(2026, 10, 6, 10, 0, 0)

    fin = calcular_fin_gracia(inicio)

    momento_final = inicio + timedelta(days=4)

    assert momento_final == fin
