from datetime import datetime, timedelta


def test_gracia_no_termina_antes_de_4_dias():
    ahora = datetime(2026, 10, 6, 10, 0, 0)

    gracia_hasta = ahora + timedelta(days=4)

    momento_antes = ahora + timedelta(days=3, hours=23, minutes=59)

    assert momento_antes < gracia_hasta


def test_gracia_termina_exactamente_a_los_4_dias():
    ahora = datetime(2026, 10, 6, 10, 0, 0)

    gracia_hasta = ahora + timedelta(days=4)

    momento_final = ahora + timedelta(days=4)

    assert momento_final >= gracia_hasta
