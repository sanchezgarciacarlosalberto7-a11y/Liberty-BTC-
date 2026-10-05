import sys
from pathlib import Path

# Permite importar bot_prestamos.py desde /opt/liberty-btc
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bot_prestamos import autorizado_para_contrato, ADMIN_ID


def prestamo(solicitante_id, tomador_id):
    return {
        "public_id": "TEST-001",
        "solicitante_id": solicitante_id,
        "tomador_id": tomador_id,
    }


def test_prestamista_puede_operar_su_prestamo():
    p = prestamo(100, 200)

    autorizado, motivo = autorizado_para_contrato(p, 100)

    assert autorizado is True


def test_prestatario_puede_operar_su_prestamo():
    p = prestamo(100, 200)

    autorizado, motivo = autorizado_para_contrato(p, 200)

    assert autorizado is True


def test_usuario_externo_no_puede_operar():
    p = prestamo(100, 200)

    autorizado, motivo = autorizado_para_contrato(p, 999)

    assert autorizado is False


def test_prestamista_no_puede_operar_prestamo_ajeno():
    prestamo_a = prestamo(100, 200)
    prestamo_b = prestamo(300, 400)

    autorizado, motivo = autorizado_para_contrato(
        prestamo_b,
        prestamo_a["solicitante_id"]
    )

    assert autorizado is False


def test_prestatario_no_puede_operar_prestamo_ajeno():
    prestamo_a = prestamo(100, 200)
    prestamo_b = prestamo(300, 400)

    autorizado, motivo = autorizado_para_contrato(
        prestamo_b,
        prestamo_a["tomador_id"]
    )

    assert autorizado is False


def test_admin_no_debe_estar_autorizado_si_no_se_permite_admin():
    p = prestamo(100, 200)

    autorizado, motivo = autorizado_para_contrato(
        p,
        ADMIN_ID,
        permitir_admin=False
    )

    assert autorizado is False


def test_admin_puede_estar_autorizado_si_se_permite_admin():
    p = prestamo(100, 200)

    autorizado, motivo = autorizado_para_contrato(
        p,
        ADMIN_ID,
        permitir_admin=True
    )

    assert autorizado is True
