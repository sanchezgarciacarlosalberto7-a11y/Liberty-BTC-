import sys
from pathlib import Path

from hypothesis import given, strategies as st

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bot_prestamos import autorizado_para_contrato


def crear_prestamo(prestamista, prestatario):
    return {
        "public_id": "TEST-MULTISIG-001",
        "solicitante_id": prestamista,
        "tomador_id": prestatario,
    }


@given(
    atacante=st.integers(min_value=1, max_value=10_000_000),
    prestamista=st.integers(min_value=1, max_value=10_000_000),
    prestatario=st.integers(min_value=1, max_value=10_000_000),
)
def test_atacante_no_puede_acceder_al_multisig(
    atacante,
    prestamista,
    prestatario,
):
    # El atacante debe ser una tercera persona.
    if atacante in (prestamista, prestatario):
        return

    p = crear_prestamo(prestamista, prestatario)

    autorizado, motivo = autorizado_para_contrato(
        p,
        atacante,
        permitir_admin=False,
    )

    assert autorizado is False


@given(
    atacante=st.integers(min_value=1, max_value=10_000_000),
    prestamista=st.integers(min_value=1, max_value=10_000_000),
    prestatario=st.integers(min_value=1, max_value=10_000_000),
)
def test_atacante_no_puede_firmar_por_un_participante(
    atacante,
    prestamista,
    prestatario,
):
    if atacante in (prestamista, prestatario):
        return

    p = crear_prestamo(prestamista, prestatario)

    autorizado, motivo = autorizado_para_contrato(
        p,
        atacante,
        permitir_admin=False,
    )

    assert autorizado is False
