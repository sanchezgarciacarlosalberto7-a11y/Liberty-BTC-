import sys
import asyncio

sys.path.insert(0, "/opt/liberty-btc")

import bot_prestamos


class FakeMessage:
    def __init__(self):
        self.text = "2099-01-01 12:00"
        self.respuestas = []

        # Simula un mensaje enviado por un grupo
        # en nombre de un administrador anónimo.
        self.sender_chat = type(
            "Chat",
            (),
            {
                "id": -100123456789,
                "type": "supergroup",
            },
        )()

    async def reply_text(self, texto):
        self.respuestas.append(texto)


class FakeUser:
    def __init__(self):
        self.id = 12345
        self.username = "usuario_real"


class FakeUpdateAnonimo:
    def __init__(self):
        self.message = FakeMessage()

        # Telegram puede conservar effective_user,
        # por eso NO usamos None como única detección.
        self.effective_user = FakeUser()


class FakeBot:
    async def send_message(self, *args, **kwargs):
        raise AssertionError(
            "Un anuncio anónimo no debe llegar a publicarse"
        )


class FakeContext:
    def __init__(self):
        self.user_data = {
            "moneda": "COP",
            "min": 500000,
            "max": 500000,
            "pago": "Nequi",
            "interes": 2,
            "tipo_anuncio": "SOLICITUD",
        }
        self.bot = FakeBot()


def test_publicar_anonimo_por_sender_chat_no_publica():
    update = FakeUpdateAnonimo()
    context = FakeContext()

    asyncio.run(
        bot_prestamos.publicar(update, context)
    )

    assert context.user_data != {}

    assert update.message.respuestas == [
        "❌ No puedes publicar anuncios de forma anónima."
    ]
