def preparar_datos(tipo_anuncio=None):
    datos = {
        "moneda": "COP",
        "min": 50000,
        "max": 500000,
        "pago": "Nequi",
        "interes": 2,
    }

    if tipo_anuncio is not None:
        datos["tipo_anuncio"] = tipo_anuncio

    return datos


def puede_publicar(datos):
    campos_obligatorios = (
        "moneda",
        "min",
        "max",
        "pago",
        "interes",
        "tipo_anuncio",
    )

    return all(campo in datos for campo in campos_obligatorios)


def test_no_publicar_si_falta_tipo_anuncio():
    datos = preparar_datos()

    assert puede_publicar(datos) is False


def test_publicar_oferta_con_tipo_anuncio():
    datos = preparar_datos("OFERTA")

    assert puede_publicar(datos) is True
    assert datos["tipo_anuncio"] == "OFERTA"


def test_publicar_solicitud_con_tipo_anuncio():
    datos = preparar_datos("SOLICITUD")

    assert puede_publicar(datos) is True
    assert datos["tipo_anuncio"] == "SOLICITUD"
