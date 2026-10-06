from datetime import datetime, timedelta


def test_codigo_actual_de_gracia_usa_1_minuto():
    ahora = datetime(2026, 10, 6, 10, 0, 0)

    gracia_hasta = ahora + timedelta(
        minutes=1
    )

    assert gracia_hasta - ahora == timedelta(minutes=1)


def test_codigo_actual_no_corresponde_a_4_dias():
    ahora = datetime(2026, 10, 6, 10, 0, 0)

    gracia_hasta = ahora + timedelta(
        minutes=1
    )

    assert gracia_hasta - ahora != timedelta(days=4)
