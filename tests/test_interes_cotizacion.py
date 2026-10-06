import sys
from pathlib import Path
import asyncio

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import bot_prestamos


class FakeDB:
    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def execute(self, *args, **kwargs):
        return self

    def fetchone(self):
        return None

    def commit(self):
        pass


class FakeBot:
    async def send_message(self, **kwargs):
        return None


class FakeContext:
    def __init__(self):
        self.bot = FakeBot()


def test_cotizacion_usa_monto_con_interes(monkeypatch):
    llamado = {}

    async def fake_yadio_sats(monto, moneda):
        llamado["monto"] = monto
        llamado["moneda"] = moneda
        return 100_000_000, 1_000_000

    def fake_calcular_ltv(monto, sats, precio):
        return 50.0

    def fake_multisig(vencimiento):
        return {
            "direccion": "tb1qtest",
            "script": "script",
            "locktime": 0,
            "prestamista_pubkey": "pub1",
            "prestatario_pubkey": "pub2",
            "prestamista_privkey": "priv1",
            "prestatario_privkey": "priv2",
            "admin_pubkey": "pub3",
            "admin_privkey": "priv3",
        }

    monkeypatch.setattr(bot_prestamos, "yadio_sats", fake_yadio_sats)
    monkeypatch.setattr(bot_prestamos, "calcular_ltv", fake_calcular_ltv)
    monkeypatch.setattr(
        bot_prestamos,
        "crear_multisig_prestamo",
        fake_multisig
    )
    monkeypatch.setattr(
        bot_prestamos,
        "con",
        lambda: FakeDB()
    )
    monkeypatch.setattr(
        bot_prestamos,
        "prestamista_id",
        lambda a: 123
    )

    anuncio = {
        "public_id": "TEST-INTERES",
        "monto_final": 500_000,
        "moneda": "COP",
        "interes": 2.0,
        "tipo_anuncio": "SOLICITUD",
        "solicitante_id": 123,
        "vencimiento": "2030-01-01 00:00",
    }

    contexto = FakeContext()

    asyncio.run(
        bot_prestamos.cotizar(anuncio, contexto)
    )

    # 500.000 + 2% = 510.000
    assert llamado["monto"] == 510_000
    assert llamado["moneda"] == "COP"
