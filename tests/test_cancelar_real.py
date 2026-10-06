import sys
import asyncio

sys.path.insert(0, "/opt/liberty-btc")

import bot_prestamos
from telegram.ext import ConversationHandler


class FakeMessage:
    def __init__(self):
        self.textos = []

    async def reply_text(self, texto):
        self.textos.append(texto)


class FakeUser:
    def __init__(self):
        self.message = FakeMessage()
        self.effective_user = type("User", (), {"id": 12345})()


class FakeContext:
    def __init__(self):
        self.args = []
        self.user_data = {
            "tipo_anuncio": "SOLICITUD",
            "moneda": "COP",
            "monto_final": 500000,
        }


def test_cancelar_real_termina_conversacion():
    user = FakeUser()
    context = FakeContext()

    resultado = asyncio.run(
        bot_prestamos.cancelar(user, context)
    )

    assert resultado == ConversationHandler.END
    assert context.user_data == {}
    assert user.message.textos == [
        "❌ Operación cancelada."
    ]
