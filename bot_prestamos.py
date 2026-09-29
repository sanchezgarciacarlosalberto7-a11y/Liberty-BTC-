"""Anuncios BTC on-chain. Requiere: pip install python-telegram-bot"""

import sys
import coincurve
import asyncio
import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)

logger = logging.getLogger(__name__)

print("PYTHON DEL BOT:", sys.executable)
print("COINCURVE DEL BOT:", coincurve.__file__)

from coincurve import PrivateKey
from gestion_ltv import calcular_ltv, obtener_estado_ltv, evaluar_prestamo
try:
    k = PrivateKey()
    print("SECP256K1 DEL BOT: OK")
except Exception as e:
    print("SECP256K1 DEL BOT: ERROR:", repr(e))


import asyncio
import base64
import json
import sqlite3
import urllib.request
import uuid
import secrets

from datetime import datetime, timezone,timedelta
from decimal import Decimal, ROUND_UP

from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Update
)

from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters
)

import bitcoin_testnet


from bitcointx import select_chain_params

from bitcointx.core.script import (
    CScript,
    OP_2,
    OP_3,
    OP_IF,
    OP_ELSE,
    OP_ENDIF,
    OP_DROP,
    OP_CHECKSIG,
    OP_CHECKMULTISIG,
    OP_CHECKLOCKTIMEVERIFY,
)

from bitcointx.core.key import CPubKey

from bitcointx.wallet import P2WSHBitcoinTestnetAddress
from coincurve import PrivateKey

select_chain_params("bitcoin/testnet")

TOKEN = "[REDACTED]"
CANAL_ANUNCIOS = "@prestamostest"
DB = "prestamos.db"
# Deben coincidir con bitcoin.conf. Bitcoin Core se ejecuta en testnet por ahora.
BITCOIN_RPC_URL = "http://127.0.0.1:48332"
BITCOIN_RPC_USER = "bot_prestamos"
BITCOIN_RPC_PASSWORD = "[REDACTED]"
MONEDA, MONTO, PAGO, INTERES, VENCE, MONTO_TOMADOR = range(6)
from datetime import datetime, timezone, timedelta
from decimal import Decimal

# =========================
# CONFIGURACIÓN LTV
# =========================

LTV_INICIAL = Decimal("0.50")
LTV_MAXIMO = Decimal("85.0")
DIAS_GRACIA = 4
ADMIN_ID = 6944462999
MOVER_CONTRATO, MOVER_DIRECCION, MOVER_CONFIRMAR = range(5, 8)
FIRMAR_CONTRATO, RECIBIR_FIRMA = range(8, 10)

def con():
    c=sqlite3.connect(DB); c.row_factory=sqlite3.Row; return c

# ============================================================
# SEGURIDAD / AUDITORÍA
# ============================================================

ADMIN_ID =6944462999  # <-- reemplazar por tu Telegram ID real

ACCIONES_SENSIBLES = {
    "MOVER_FONDOS",
    "CAMBIAR_DESTINO",
    "FIRMAR",
    "TRANSMITIR",
    "CREAR_PSBT",
    "LIQUIDAR",
    "CAMBIAR_ESTADO",
}


async def log_evento(
    context,
    accion,
    public_id=None,
    usuario_id=None,
    autorizado=None,
    motivo=None,
    resultado=None,
    severidad="INFO"
):
    ahora = datetime.now(timezone.utc).isoformat()

    mensaje_log = (
        f"[{ahora}] "
        f"[{severidad}] "
        f"accion={accion} "
        f"contrato={public_id or '-'} "
        f"usuario={usuario_id or '-'} "
        f"autorizado={autorizado} "
        f"motivo={motivo or '-'} "
        f"resultado={resultado or '-'}"
    )

    print(mensaje_log)

    try:
        with con() as db:

            db.execute(
                """
                CREATE TABLE IF NOT EXISTS auditoria(
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    fecha TEXT NOT NULL,
                    severidad TEXT NOT NULL,
                    accion TEXT NOT NULL,
                    public_id TEXT,
                    usuario_id INTEGER,
                    autorizado INTEGER,
                    motivo TEXT,
                    resultado TEXT
                )
                """
            )

            db.execute(
                """
                INSERT INTO auditoria(
                    fecha,
                    severidad,
                    accion,
                    public_id,
                    usuario_id,
                    autorizado,
                    motivo,
                    resultado
                )
                VALUES(?,?,?,?,?,?,?,?)
                """,
                (
                    ahora,
                    severidad,
                    accion,
                    public_id,
                    usuario_id,
                    None if autorizado is None
                    else int(autorizado),
                    motivo,
                    resultado
                )
            )

            db.commit()

    except Exception as e:

        print(
            "❌ ERROR GUARDANDO AUDITORÍA:",
            repr(e)
        )


async def alertar_admin(
    context,
    accion,
    public_id,
    usuario_id,
    motivo,
    resultado="BLOQUEADA"
):

    if not ADMIN_ID:
        return

    texto = (
        "🚨 ALERTA DE SEGURIDAD\n\n"
        f"🔧 Acción: {accion}\n"
        f"🆔 Contrato: {public_id or '-'}\n"
        f"👤 Usuario: {usuario_id or '-'}\n\n"
        f"🔐 Autorización: ❌ DENEGADA\n"
        f"📌 Motivo: {motivo}\n\n"
        f"📊 Resultado: {resultado}"
    )

    try:

        await context.bot.send_message(
            ADMIN_ID,
            texto
        )

    except Exception as e:

        print(
            "❌ ERROR ENVIANDO ALERTA AL ADMIN:",
            repr(e)
        )

def usuario_es_participante(prestamo, usuario_id):

    return usuario_id in {
        prestamo["solicitante_id"],
        prestamo["tomador_id"]
    }


def usuario_es_admin(usuario_id):

    return usuario_id == ADMIN_ID


def autorizado_para_contrato(
    prestamo,
    usuario_id,
    permitir_admin=False
):

    if usuario_id == prestamo["solicitante_id"]:
        return True, "Usuario es PRESTAMISTA"

    if usuario_id == prestamo["tomador_id"]:
        return True, "Usuario es PRESTATARIO"

    if permitir_admin and usuario_id == ADMIN_ID:
        return True, "Usuario es ADMIN"

    return False, "Usuario no pertenece al contrato"


async def comprobar_autorizacion(
    context,
    prestamo,
    usuario_id,
    accion,
    permitir_admin=False
):

    public_id = prestamo["public_id"]

    autorizado, motivo = autorizado_para_contrato(
        prestamo,
        usuario_id,
        permitir_admin=permitir_admin
    )

    if autorizado:

        await log_evento(
            context=context,
            accion=accion,
            public_id=public_id,
            usuario_id=usuario_id,
            autorizado=True,
            motivo=motivo,
            resultado="PERMITIDA",
            severidad="INFO"
        )

        return True

    await log_evento(
        context=context,
        accion=accion,
        public_id=public_id,
        usuario_id=usuario_id,
        autorizado=False,
        motivo=motivo,
        resultado="BLOQUEADA",
        severidad="WARNING"
    )

    await alertar_admin(
        context=context,
        accion=accion,
        public_id=public_id,
        usuario_id=usuario_id,
        motivo=motivo,
        resultado="BLOQUEADA"
    )

    return False

 
def crear_db():
    with con() as c:

        esquema = c.execute("""
            SELECT sql
            FROM sqlite_master
            WHERE type='table' AND name='anuncios'
        """).fetchone()

        anterior = bool(
            esquema and
            "CHECK (estado IN" in (esquema['sql'] or '')
        )

        if anterior:
            c.execute("ALTER TABLE anuncios RENAME TO anuncios_anterior")

        c.execute("""
            CREATE TABLE IF NOT EXISTS anuncios(
                id INTEGER PRIMARY KEY,
                public_id TEXT UNIQUE,
                solicitante_id INTEGER,
                solicitante_username TEXT,
                tomador_id INTEGER,
                tomador_username TEXT,
                moneda TEXT,
                monto_min INTEGER,
                monto_max INTEGER,
                monto_final INTEGER,
                metodo_pago TEXT,
                fecha TEXT,
                vencimiento TEXT,
                estado TEXT,
                cotizacion_btc TEXT,
                deposito_sats INTEGER,
                canal_chat_id TEXT,
                mensaje_canal_id INTEGER
            )
        """)

        if anterior:
            c.execute("""
                INSERT INTO anuncios(
                    id,
                    solicitante_id,
                    solicitante_username,
                    moneda,
                    monto_min,
                    monto_max,
                    metodo_pago,
                    fecha,
                    estado
                )
                SELECT
                    id,
                    solicitante_id,
                    solicitante_username,
                    moneda,
                    monto_min,
                    monto_max,
                    metodo_pago,
                    fecha,
                    estado
                FROM anuncios_anterior
            """)

            c.execute("DROP TABLE anuncios_anterior")

        # Comprobar columnas actuales
        actuales = {
            x[1]
            for x in c.execute(
                "PRAGMA table_info(anuncios)"
            ).fetchall()
        }

        # Columnas adicionales
        extras = {
            "public_id": "TEXT",
            "tomador_id": "INTEGER",
            "tomador_username": "TEXT",
            "monto_final": "INTEGER",
            "vencimiento": "TEXT",
            "cotizacion_btc": "TEXT",
            "deposito_sats": "INTEGER",
            "canal_chat_id": "TEXT",
            "mensaje_canal_id": "INTEGER",
            "ltv_actual": "TEXT",
            "ltv_maximo": "TEXT",
            "gracia_inicio": "TEXT",
            "gracia_hasta": "TEXT",
            "estado_liquidacion": "TEXT",
            "estado_disputa": "TEXT",
            "disputa_abierta_por_id": "INTEGER",
            "disputa_abierta_por_username": "TEXT",
            "disputa_fecha": "TEXT",

            # Multisig
            "multisig_address": "TEXT",
            "witness_script": "TEXT",
            "locktime": "INTEGER",
            "prestamista_pubkey": "TEXT",
            "prestatario_pubkey": "TEXT",
            "prestamista_privkey": "TEXT",
            "prestatario_privkey": "TEXT",
            "admin_pubkey": "TEXT",
            "admin_privkey": "TEXT",
            "interes": "REAL",

            # Depósito BTC
            "collateral_txid": "TEXT",
            "collateral_vout": "INTEGER",

            # PSBT / destino
            "direccion_destino": "TEXT",
            "direccion_destino_username": "TEXT",
            "direccion_destino_rol": "TEXT",
            "psbt": "TEXT",
            "firma_prestamista": "TEXT",
            "firma_prestatario": "TEXT",
            "firma_admin": "TEXT",
            "usuario_bloqueado_direccion": "INTEGER",
        } 
        

        for nombre, tipo in extras.items():
            if nombre not in actuales:
                c.execute(
                    f"ALTER TABLE anuncios ADD COLUMN {nombre} {tipo}"
                )

        c.commit()


    c.execute("CREATE UNIQUE INDEX IF NOT EXISTS anuncios_public_id ON anuncios(public_id)")
def pid(): return "PRE-"+datetime.now(timezone.utc).strftime("%Y%m%d")+"-"+uuid.uuid4().hex.upper()
def fmt(n): return f"{n:,}".replace(",", ".")
def monto(texto):
    p = texto.strip().replace(" ", "").split("-")

    if len(p) not in (1, 2):
        return None

    try:
        v = []

        for x in p:
            # Solo números enteros
            if not x.isdigit():
                return None

            n = int(x)

            if n <= 0:
                return None

            v.append(n)

    except ValueError:
        return None

    a, b = (v[0], v[0]) if len(v) == 1 else v

    return (a, b) if a <= b else None
def tarjeta(a):
    valor = (
        f"${fmt(a['monto_min'])}"
        if a['monto_min'] == a['monto_max']
        else f"${fmt(a['monto_min'])} - ${fmt(a['monto_max'])}"
    )

    return (
        f"💰 SOLICITUD DE PRÉSTAMO FIAT\n"
        f"💵 Moneda: {a['moneda']}\n"
        f"💰 Monto: {valor}\n"
        f"💳 Pago: {a['metodo_pago']}\n"
        f"📈 Interés: {a['interes']}%\n"
        f"⏳ Vence: {a['vencimiento']} UTC\n"
        f"📌 {a['estado']}\n"
        f"🆔 ID: {a['public_id']}"
    )
async def yadio_sats(valor, moneda):

    def leer():
        with urllib.request.urlopen(
            "https://api.yadio.io/exrates/BTC",
            timeout=30
        ) as r:
            return json.load(r)

    datos = await asyncio.to_thread(leer)

    precio = Decimal(str(datos['BTC'][moneda]))

    # LTV_MAXIMO = 0.50 significa 50%
    valor_colateral = (
        Decimal(str(valor)) / LTV_INICIAL
    )

    print("💵 VALOR PRÉSTAMO:", valor)
    print("📊 LTV INICIAL:", LTV_INICIAL)
    print("🔒 VALOR COLATERAL:", valor_colateral)
    print("₿ PRECIO BTC:", precio)

    sats = int(
        (
            valor_colateral
            / precio
            * Decimal("100000000")
        ).to_integral_value(rounding=ROUND_UP)
    )

    print("🪙 SATS CALCULADOS:", sats)

    return precio, sats
def calcular_ltv(monto_prestamo, deposito_sats, precio_btc):
    """
    Calcula el LTV del préstamo.

    LTV = deuda / valor del colateral × 100
    """

    if deposito_sats <= 0:
        raise ValueError("El colateral debe ser mayor que 0")

    if precio_btc <= 0:
        raise ValueError("El precio de BTC debe ser mayor que 0")

    monto_prestamo = Decimal(str(monto_prestamo))
    deposito_sats = Decimal(str(deposito_sats))
    precio_btc = Decimal(str(precio_btc))

    valor_colateral = (
        deposito_sats / Decimal("100000000")
    ) * precio_btc

    ltv = (
        monto_prestamo / valor_colateral
    ) * Decimal("100")

    return ltv

async def rpc_core(metodo, parametros=None):
    """Llamada local a Bitcoin Core RPC; nunca expone claves de usuarios."""

    def llamar():
        cuerpo = json.dumps({
            'jsonrpc': '1.0',
            'id': 'bot-prestamos',
            'method': metodo,
            'params': parametros or []
        }).encode()

        token = base64.b64encode(
            f"{BITCOIN_RPC_USER}:{BITCOIN_RPC_PASSWORD}".encode()
        ).decode()

        req = urllib.request.Request(
            BITCOIN_RPC_URL,
            data=cuerpo,
            headers={
                'Content-Type': 'application/json',
                'Authorization': 'Basic ' + token
            }
        )

        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                respuesta = json.load(r)

        except urllib.error.HTTPError as e:
            cuerpo_error = e.read().decode("utf-8", errors="replace")
            raise RuntimeError(
                f"HTTP {e.code} desde Bitcoin Core: {cuerpo_error}"
            )

        except urllib.error.URLError as e:
            raise RuntimeError(
                f"Error de conexión con Bitcoin Core: {e}"
            )

        if respuesta.get('error'):
            raise RuntimeError(respuesta['error']['message'])

        return respuesta['result']

    return await asyncio.to_thread(llamar)

async def start(u,c): await u.message.reply_text("Usa /prestamo. Consulta /mis_anuncios o /mis_tomas.")
async def nodo(u,c):
    try:
        cadena=await rpc_core('getblockchaininfo')
        progreso=Decimal(str(cadena['verificationprogress']))*100
        await u.message.reply_text(f"✅ Bitcoin Core conectado\nRed: {cadena['chain']}\nBloques: {cadena['blocks']}\nSincronización: {progreso:.2f}%")
    except Exception as e:
        detalle=str(e).replace(BITCOIN_RPC_PASSWORD, "[oculta]")
        await u.message.reply_text("❌ No se pudo conectar a Bitcoin Core.\nDetalle: "+detalle[:180])
async def iniciar(u,c): c.user_data.clear(); await u.message.reply_text("Moneda (COP, USD):"); return MONEDA

MONEDAS_PERMITIDAS = ["COP", "USD", "EUR"]

async def moneda(u, c):
    x = u.message.text.strip().upper()
    if x not in MONEDAS_PERMITIDAS:
        await u.message.reply_text("Moneda inválida.")
        return MONEDA

    c.user_data['moneda'] = x

    await u.message.reply_text(
        "Monto exacto o rango: 500000 o 500000-1000000"
    )
    return MONTO

async def rango(u, c):
    x = monto(u.message.text)

    if not x:
        await u.message.reply_text("❌ Monto inválido.")
        return MONTO

    minimo, maximo = x
    moneda = c.user_data.get('moneda')

    if moneda == "COP":

        if minimo < 14000:
            await u.message.reply_text(
                "❌ El monto mínimo es 14.000 COP."
            )
            return MONTO

        if maximo > 1000000:
            await u.message.reply_text(
                "❌ El monto máximo es 1.000.000 COP."
            )
            return MONTO

    elif moneda == "USD":

        if minimo < 5:
            await u.message.reply_text(
                "❌ El monto mínimo es 5 USD."
            )
            return MONTO

        if maximo > 1000:
            await u.message.reply_text(
                "❌ El monto máximo es 1000 USD."
            )
            return MONTO

    else:
        await u.message.reply_text("❌ Moneda no seleccionada.")
        return MONEDA

    c.user_data['min'] = minimo
    c.user_data['max'] = maximo

    await u.message.reply_text(
        f"Monto: {minimo:,.0f} - {maximo:,.0f} {moneda}\n"
        "Método de pago fiat:"
    )

    return PAGO

async def pago(u, c):
    x = u.message.text.strip()

    if not x:
        await u.message.reply_text("Indica un método de pago.")
        return PAGO

    c.user_data['pago'] = x[:100]

    await u.message.reply_text(
        "📈 ¿Qué interés deseas cobrar?\n"
        "Ejemplo: 2"
    )

    return INTERES

async def interes(u, c):
    try:
        x = float(u.message.text.strip().replace(",", "."))

        if x <= 0 or x > 100:
            raise ValueError

    except ValueError:
        await u.message.reply_text(
            "❌ Interés inválido.\n"
            "Introduce un porcentaje entre 0 y 100.\n"
            "Ejemplo: 2"
        )
        return INTERES

    c.user_data['interes'] = x

    await u.message.reply_text(
        "Vencimiento BTC UTC: AAAA-MM-DD HH:MM"
    )

    return VENCE
async def publicar(u,c):
    try:
        v=datetime.strptime(u.message.text.strip(),"%Y-%m-%d %H:%M").replace(tzinfo=timezone.utc)
        if v<=datetime.now(timezone.utc): raise ValueError
    except ValueError: await u.message.reply_text("Fecha inválida o pasada."); return VENCE
    i=pid(); usr=u.effective_user
    with con() as x:
        x.execute(
    """
    INSERT INTO anuncios(
        public_id,
        solicitante_id,
        solicitante_username,
        moneda,
        monto_min,
        monto_max,
        metodo_pago,
        fecha,
        vencimiento,
        estado,
        interes
    )
    VALUES(?,?,?,?,?,?,?,?,?,?,?)
    """,
    (
        i,
        usr.id,
        usr.username,
        c.user_data['moneda'],
        c.user_data['min'],
        c.user_data['max'],
        c.user_data['pago'],
        datetime.now(timezone.utc).isoformat(),
        v.strftime("%Y-%m-%d %H:%M"),
        "PUBLICADO",
        c.user_data['interes']
    )
)
        a=x.execute("SELECT * FROM anuncios WHERE public_id=?",(i,)).fetchone()
    m=await c.bot.send_message(CANAL_ANUNCIOS,tarjeta(a),reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🙋 Tomar anuncio",callback_data="tomar:"+i)]]))
    with con() as x: x.execute("UPDATE anuncios SET canal_chat_id=?,mensaje_canal_id=? WHERE public_id=?",(str(m.chat_id),m.message_id,i))
    await u.message.reply_text("✅ Publicado. ID: "+i); c.user_data.clear(); return ConversationHandler.END

async def cotizar(a, c):

    try:
        precio, sats = await yadio_sats(
            a['monto_final'],
            a['moneda']
        )

        ltv = calcular_ltv(
            a['monto_final'],
            sats,
            precio
        )

        print(f"📊 LTV: {ltv:.2f}%")

    except Exception as e:
        print("Error cotizando BTC:", e)

        with con() as x:
            x.execute(
                "UPDATE anuncios SET estado='ERROR_COTIZACION' "
                "WHERE public_id=?",
                (a['public_id'],)
            )
            x.commit()

        return False


    # ============================================================
    # CREAR MULTISIG TESTNET
    # ============================================================

    try:
        multisig = crear_multisig_prestamo(
            a['vencimiento']
        )

        print("=== MULTISIG GENERADO ===")
        print("ADMIN PUBKEY:", repr(multisig["admin_pubkey"]))
        print("ADMIN PRIVKEY:", repr(multisig["admin_privkey"]))
        print("=========================")

    except Exception as e:
        print("Error creando multisig:", e)

        with con() as x:
            x.execute(
                "UPDATE anuncios SET estado='ERROR_MULTISIG' "
                "WHERE public_id=?",
                (a['public_id'],)
            )
            x.commit()

        return False


    # ============================================================
    # GUARDAR INFORMACIÓN DEL MULTISIG
    # ============================================================

    with con() as x:
        x.execute(
            """
            UPDATE anuncios
            SET
                estado='DEPOSITO_BTC_PENDIENTE',
                cotizacion_btc=?,
                deposito_sats=?,
                ltv_actual=?,
                ltv_maximo=?,
                estado_liquidacion='NORMAL',
                multisig_address=?,
                witness_script=?,
                locktime=?,
                prestamista_pubkey=?,
                prestatario_pubkey=?,
                prestamista_privkey=?,
                prestatario_privkey=?,
                admin_pubkey=?,
                admin_privkey=?
            WHERE public_id=?
            """,
            (
                str(precio),
                sats,
                str(ltv),
                str("LTV_INICIAL"),
                multisig["direccion"],
                multisig["script"],
                multisig["locktime"],
                multisig["prestamista_pubkey"],
                multisig["prestatario_pubkey"],
                multisig["prestamista_privkey"],
                multisig["prestatario_privkey"],
                multisig["admin_pubkey"],
                multisig["admin_privkey"],
                a["public_id"]
            )
        )

        x.commit()


    # ============================================================
    # AVISAR AL PRESTAMISTA
    # ============================================================

    await c.bot.send_message(
        chat_id=a['solicitante_id'],
        text=f"""🔐 MULTISIG TESTNET CREADO

🆔 Préstamo:
{a['public_id']}

💰 Préstamo:
{fmt(a['monto_final'])} {a['moneda']}

₿ Colateral requerido:
{Decimal(sats) / Decimal("100000000"):.8f} BTC

📍 Dirección multisig:
{multisig['direccion']}

⏰ Vencimiento:
{a['vencimiento']} UTC

⚠️ TESTNET
No envíes BTC reales.
""",
        parse_mode=None
    )


    # ============================================================
    # AVISAR AL TOMADOR
    # ============================================================

    await c.bot.send_message(
        chat_id=a['tomador_id'],
        text=f"""✅ PRÉSTAMO TOMADO

🆔 Contrato:
{a['public_id']}

💵 Monto:
{fmt(a['monto_final'])} {a['moneda']}

₿ Colateral requerido:
{Decimal(sats) / Decimal("100000000"):.8f} BTC

⏰ Vencimiento:
{a['vencimiento']} UTC

⏳ ESPERANDO DEPÓSITO

El prestamista debe depositar el colateral BTC
en la dirección multisig.
""",
        parse_mode=None
    )


    return True

async def tomar(u, c):

    q = u.callback_query
    await q.answer()

    i = q.data.split(':', 1)[1]
    usr = q.from_user

    with con() as x:

        # ========================================================
        # BUSCAR EL ANUNCIO
        # ========================================================

        a = x.execute(
            "SELECT * FROM anuncios WHERE public_id=?",
            (i,)
        ).fetchone()

        if not a or a['estado'] != 'PUBLICADO':
            return ConversationHandler.END

        if a['solicitante_id'] == usr.id:
            return ConversationHandler.END

        # ========================================================
        # LÍMITE DE 3 PRÉSTAMOS TOMADOS
        # ========================================================

        cantidad = x.execute(
            """
            SELECT COUNT(*)
            FROM anuncios
            WHERE tomador_id=?
            AND estado IN('TOMADO_ESPERANDO_MONTO',
            'DEPOSITO_BTC_PENDIENTE'
         )
            """,
            (usr.id,)
        ).fetchone()[0]

        if cantidad >= 3:

            await c.bot.send_message(
                usr.id,
                "🚫 Límite alcanzado.\n\n"
                "Solo puedes tener 2 préstamos "
                "esperando confirmación del monto.\n\n"
                "Debes completar o cancelar uno antes "
                "de tomar otro anuncio."
            )

            return ConversationHandler.END

        # ========================================================
        # DETERMINAR TIPO DE ANUNCIO
        # ========================================================

        rango = a['monto_min'] != a['monto_max']

        e = (
            'TOMADO_ESPERANDO_MONTO'
            if rango
            else 'DEPOSITO_BTC_PENDIENTE'
        )

        # ========================================================
        # TOMAR EL ANUNCIO
        # ========================================================

        x.execute(
    """
    UPDATE anuncios
    SET
        tomador_id=?,
        tomador_username=?,
        monto_final=?,
        estado=?
    WHERE public_id=?
    """,
    (
        usr.id,
        usr.username,
        None if rango else a['monto_min'],
        e,
        i
    )
)

        # Volver a cargar el anuncio actualizado
        a = x.execute(
            "SELECT * FROM anuncios WHERE public_id=?",
            (i,)
        ).fetchone()

    # ============================================================
    # ELIMINAR EL MENSAJE DEL ANUNCIO
    # ============================================================

    try:
        await q.message.delete()
    except Exception:
        pass

    # ============================================================
    # SI ES UN RANGO, PEDIR EL MONTO
    # ============================================================

    if rango:

        c.user_data['tomando'] = i

        await c.bot.send_message(
            usr.id,
            f"Monto exacto para {i}: "
            f"{a['monto_min']} - {a['monto_max']} {a['moneda']}"
        )

        return MONTO_TOMADOR

    # ============================================================
    # SI ES MONTO FIJO, COTIZAR DIRECTAMENTE
    # ============================================================

    await cotizar(a, c)

    return ConversationHandler.END
async def monto_tomador(u, c):
    i = c.user_data.get('tomando')
    x = monto(u.message.text)

    if not i or not x or x[0] != x[1]:
        await u.message.reply_text(
            "Escribe un único monto válido."
        )
        return MONTO_TOMADOR

    with con() as z:
        a = z.execute(
            "SELECT * FROM anuncios WHERE public_id=?",
            (i,)
        ).fetchone()

        if not a:
            await u.message.reply_text(
                "❌ El anuncio ya no existe."
            )
            return ConversationHandler.END

        if a['tomador_id'] != u.effective_user.id:
            await u.message.reply_text(
                "❌ No eres el tomador de este anuncio."
            )
            return ConversationHandler.END

        if not a['monto_min'] <= x[0] <= a['monto_max']:
            await u.message.reply_text(
                "❌ El monto está fuera del rango del anuncio."
            )
            return MONTO_TOMADOR

        z.execute(
            """
            UPDATE anuncios
            SET monto_final=?
            WHERE public_id=?
            """,
            (x[0], i)
        )

        a = z.execute(
            "SELECT * FROM anuncios WHERE public_id=?",
            (i,)
        ).fetchone()

    c.user_data.pop('tomando', None)

    await cotizar(a, c)

    return ConversationHandler.END
async def listar(u, c, toma=False):

    # ============================================================
    # OBTENER OPERACIONES
    # ============================================================

    with con() as x:

        if toma:
            # /mis_tomas:
            # Mostrar todas las operaciones donde el usuario
            # participa como TOMADOR o SOLICITANTE.

            filas = x.execute(
                """
                SELECT
                    public_id,
                    estado,
                    monto_min,
                    monto_max,
                    monto_final,
                    moneda,
                    tomador_id,
                    solicitante_id,
                    tomador_username,
                    solicitante_username
                FROM anuncios
                WHERE (tomador_id = ?
                   OR solicitante_id = ?)
                   AND estado IN (
              'COLATERAL_CONFIRMADO',
              'PSBT_CREADA',
              'TRANSMITIDA'
          )
                ORDER BY id DESC
                LIMIT 6
                """,
                (
                    u.effective_user.id,
                    u.effective_user.id
                )
            ).fetchall()

        else:
            # Listado normal:
            # Mostrar operaciones creadas por el solicitante.

            filas = x.execute(
                """
                SELECT
                    public_id,
                    estado,
                    monto_min,
                    monto_max,
                    monto_final,
                    moneda,
                    tomador_id,
                    solicitante_id,
                    tomador_username,
                    solicitante_username
                FROM anuncios
                WHERE solicitante_id = ?
                AND estado IN (
              'COLATERAL_CONFIRMADO',
              'PSBT_CREADA',
              'TRANSMITIDA')
                ORDER BY id DESC
                LIMIT 6

                """,
                (u.effective_user.id,)
            ).fetchall()


    # ============================================================
    # SIN OPERACIONES
    # ============================================================

    if not filas:
        await u.message.reply_text(
            "📭 No tienes préstamos registrados."
        )
        return


    # ============================================================
    # ESTADOS ACTIVOS
    # ============================================================

    estados_activos = {
        "TOMADO_ESPERANDO_MONTO",
        "DEPOSITO_BTC_PENDIENTE",
        "COLATERAL_CONFIRMADO",
        "PSBT_CREADA",
    }


    activos = []


    # ============================================================
    # RECORRER OPERACIONES
    # ============================================================

    for a in filas:

        estado = a["estado"]


        # ========================================================
        # ESTADO: COLATERAL_CONFIRMADO
        # ========================================================

        if estado == "COLATERAL_CONFIRMADO":

            texto = (
                f"🔵 {a['public_id']}\n"
                f"🔐 Colateral confirmado\n"
                f"💰 Monto: "
                f"{fmt(a['monto_final'] or 0)} "
                f"{a['moneda']}"
            )


        # ========================================================
        # ESTADO: PSBT_CREADA
        # ========================================================

        elif estado == "PSBT_CREADA":

            texto = (
                f"🟣 {a['public_id']}\n"
                f"⏳ Transacción preparada\n"
                f"💰 Monto: "
                f"{fmt(a['monto_final'] or 0)} "
                f"{a['moneda']}"
            )


        # ========================================================
        # ESTADO: TRANSMITIDA
        # ========================================================

        elif estado == "TRANSMITIDA":

            texto = (
                f"🟢 {a['public_id']}\n"
                f"✅ Préstamo completado\n"
                f"💰 Monto: "
                f"{fmt(a['monto_final'] or 0)} "
                f"{a['moneda']}"
            )


        # ========================================================
        # ESTADOS TÉCNICOS
        # ========================================================

        elif estado in {
            "ERROR_MULTISIG",
            "PRUEBA_ANTERIOR",
        }:

            continue


        # ========================================================
        # ESTADO DESCONOCIDO
        # ========================================================

        else:

            texto = (
                f"⚪ {a['public_id']}\n"
                f"📌 Operación: {estado}\n"
                f"💰 Monto: "
                f"{fmt(a['monto_final'] or 0)} "
                f"{a['moneda']}"
            )


        # ========================================================
        # MOSTRAR CONTRAPARTE
        # ========================================================
        #
        # SOLO se ejecuta una vez por operación.
        #
        # Si yo soy el TOMADOR:
        #     muestro al SOLICITANTE.
        #
        # Si yo soy el SOLICITANTE:
        #     muestro al TOMADOR.
        #
        # Nunca muestro mi propio usuario.
        # ========================================================

        if toma:

            mi_id = u.effective_user.id

            if a["tomador_id"] == mi_id:

                if a["solicitante_username"]:
                    texto += (
                        f"\n🤝 Contraparte: "
                        f"@{a['solicitante_username']}"
                    )

            elif a["solicitante_id"] == mi_id:

                if a["tomador_username"]:
                    texto += (
                        f"\n🤝 Contraparte: "
                        f"@{a['tomador_username']}"
                    )


        # ========================================================
        # SEPARAR ACTIVOS / HISTORIAL
        # ========================================================

        if estado in estados_activos:

            activos.append(texto)


    # ============================================================
    # CONSTRUIR MENSAJE
    # ============================================================

    partes = [
        "📋 MIS PRÉSTAMOS"
    ]


    # ============================================================
    # ACTIVOS
    # ============================================================

    if activos:

        partes.append(
            "\n🔄 ACTIVOS\n\n" +
            "\n\n".join(activos)
        )


    # ============================================================
    # NADA PARA MOSTRAR
    # ============================================================

    if not activos:
       partes.append(
        "\n📭 No tienes órdenes activas."
    )


    # ============================================================
    # ENVIAR MENSAJE
    # ============================================================

    mensaje = "\n".join(partes)

    MAX_LEN = 4000

    for i in range(0, len(mensaje), MAX_LEN):

        await u.message.reply_text(
            mensaje[i:i + MAX_LEN]
        )
async def mis_anuncios(u,c): await listar(u,c)
async def mis_tomas(u,c): await listar(u,c,True)
async def disputa(update: Update, context: ContextTypes.DEFAULT_TYPE):

    usuario = update.effective_user

    # Verificar que se haya enviado el ID
    if not context.args:
        await update.message.reply_text(
            "❌ Debes indicar el ID de la operación.\n\n"
            "Ejemplo:\n"
            "/disputa PRE-XXXXXXXX"
        )
        return

    public_id = context.args[0].strip()

    with con() as c:
        a = c.execute("""
            SELECT *
            FROM anuncios
            WHERE public_id=?
        """, (public_id,)).fetchone()

    # La operación no existe
    if not a:
        await update.message.reply_text(
            f"❌ No existe la operación:\n{public_id}"
        )
        return

    # Verificar que el usuario sea una de las partes
    es_prestamista = (
        a["solicitante_id"] == usuario.id
    )

    es_tomador = (
        a["tomador_id"] == usuario.id
    )

    if not es_prestamista and not es_tomador:
        await update.message.reply_text(
            "❌ No puedes abrir una disputa de esta operación.\n\n"
            "No perteneces a ninguna de las partes."
        )
        return

    # Evitar abrir varias disputas
    estado_disputa = a["estado_disputa"]

    if estado_disputa in (
        "DISPUTA_ABIERTA",
        "DISPUTA_EN_REVISION"
    ):
        await update.message.reply_text(
            "⚠️ Esta operación ya tiene una disputa abierta.\n\n"
            f"🆔 {public_id}\n"
            f"📊 Estado: {estado_disputa}"
        )
        return

    ahora = datetime.now(timezone.utc).isoformat()

    username = usuario.username or f"id_{usuario.id}"

    # Registrar la disputa
    with con() as c:
        c.execute("""
            UPDATE anuncios
            SET
                estado_disputa=?,
                disputa_abierta_por_id=?,
                disputa_abierta_por_username=?,
                disputa_fecha=?
            WHERE public_id=?
        """, (
            "DISPUTA_ABIERTA",
            usuario.id,
            username,
            ahora,
            public_id
        ))

    # Obtener nuevamente la operación
    with con() as c:
        a = c.execute("""
            SELECT *
            FROM anuncios
            WHERE public_id=?
        """, (public_id,)).fetchone()

    prestamista = (
        f"@{a['solicitante_username']}"
        if a["solicitante_username"]
        else f"ID {a['solicitante_id']}"
    )

    tomador = (
        f"@{a['tomador_username']}"
        if a["tomador_username"]
        else f"ID {a['tomador_id']}"
    )

    quien_abre = (
        f"@{username}"
        if usuario.username
        else f"ID {usuario.id}"
    )
    # Avisar al administrador
    await context.bot.send_message(
    chat_id=ADMIN_ID,
    text=(
        "🚨 NUEVA DISPUTA\n\n"
        f"🆔 Operación:\n{public_id}\n\n"
        f"👤 Prestamista:\n{prestamista}\n\n"
        f"👤 Tomador:\n{tomador}\n\n"
        f"🚨 Abierta por:\n{quien_abre}\n\n"
        f"📊 Estado:\n{a['estado']}\n\n"
        "⚠️ Requiere revisión administrativa."
    )
)

    # Confirmación a quien abrió la disputa
    await update.message.reply_text(
        "🚨 DISPUTA ABIERTA\n\n"
        f"🆔 Operación:\n{public_id}\n\n"
        f"👤 Prestamista:\n{prestamista}\n\n"
        f"👤 Tomador:\n{tomador}\n\n"
        f"🚨 Disputa abierta por:\n{quien_abre}\n\n"
        f"📊 Estado de la operación:\n{a['estado']}\n\n"
        "La disputa ha sido enviada al administrador.\n"
        "La operación queda marcada para revisión."
    )
async def cancelar(u,c): c.user_data.clear(); await u.message.reply_text("❌ Operación cancelada."); return ConversationHandler.END

async def firmar(update: Update, context: ContextTypes.DEFAULT_TYPE):

    await update.message.reply_text(
        "✍️ FIRMAR CONTRATO\n\n"
        "Escribe el ID del contrato cuya PSBT quieres firmar.\n\n"
        "Ejemplo:\n"
        "PRE-20260830-08FE9C9BD7C44644A9B07E63C3ABDB34\n\n"
        "La firma no mueve los fondos."
    )

    return FIRMAR_CONTRATO

def generar_clave():
    return PrivateKey(
        secrets.token_bytes(32)
    )


from datetime import datetime, timezone

LOCKTIME_MIN = 500_000_000

def fecha_a_locktime(fecha_texto):
    fecha = datetime.strptime(
        fecha_texto,
        "%Y-%m-%d %H:%M"
    ).replace(tzinfo=timezone.utc)

    locktime = int(fecha.timestamp())

    # Debe ser un locktime basado en timestamp,
    # no una altura de bloque.
    if locktime < LOCKTIME_MIN:
        raise ValueError(
            "La fecha es demasiado antigua para usarla como CLTV por timestamp."
        )

    # Límite de seguridad del sistema.
    ahora = datetime.now(timezone.utc)

    if fecha <= ahora:
        raise ValueError(
            "La fecha de vencimiento debe estar en el futuro."
        )

    # Ejemplo: máximo 10 años desde ahora.
    if fecha > ahora.replace(year=ahora.year + 10):
        raise ValueError(
            "La fecha de vencimiento es demasiado lejana."
        )

    return locktime

def crear_witness_script(
    pubkey_prestamista,
    pubkey_prestatario,
    pubkey_admin,
    locktime
):

    prestamista = bytes(pubkey_prestamista)
    prestatario = bytes(pubkey_prestatario)
    admin = bytes(pubkey_admin)

    claves = sorted([
        prestamista,
        prestatario,
        admin
    ])

    return CScript([
        OP_IF,

        # 2-de-3
        OP_2,
        claves[0],
        claves[1],
        claves[2],
        OP_3,
        OP_CHECKMULTISIG,

        OP_ELSE,

        # Recuperación después del vencimiento
        locktime,
        OP_CHECKLOCKTIMEVERIFY,
        OP_DROP,

        prestamista,
        OP_CHECKSIG,

        OP_ENDIF
    ])

def crear_multisig_prestamo(vencimiento):

    locktime = fecha_a_locktime(vencimiento)

    # Generar las tres claves privadas
    prestamista = generar_clave()
    prestatario = generar_clave()
    admin = generar_clave()

    # Claves públicas comprimidas
    prestamista_pubkey = prestamista.public_key.format(compressed=True)
    prestatario_pubkey = prestatario.public_key.format(compressed=True)
    admin_pubkey = admin.public_key.format(compressed=True)

    # Crear witness script 2-de-3
    script = crear_witness_script(
        prestamista_pubkey,
        prestatario_pubkey,
        admin_pubkey,
        locktime
    )

    # Crear dirección P2WSH explícitamente en TESTNET
    direccion = P2WSHBitcoinTestnetAddress.from_redeemScript(
        script
    )

    direccion_texto = str(direccion)

    print("🔐 MULTISIG 2-DE-3 GENERADO:", direccion_texto)

    if not direccion_texto.startswith("tb1"):
        raise RuntimeError(
            f"La dirección generada NO es Testnet: {direccion_texto}"
        )

    if not direccion_texto.startswith("tb1q"):
        raise RuntimeError(
            f"La dirección generada NO es Testnet P2WSH: {direccion_texto}"
        )

    return {
        "direccion": direccion_texto,
        "script": script.hex(),
        "locktime": locktime,

        "prestamista_pubkey": prestamista_pubkey.hex(),
        "prestatario_pubkey": prestatario_pubkey.hex(),
        "admin_pubkey": admin_pubkey.hex(),

        # Solo para pruebas actuales de Testnet
        "prestamista_privkey": prestamista.secret.hex(),
        "prestatario_privkey": prestatario.secret.hex(),
        "admin_privkey": admin.secret.hex()
    }
async def mover_contrato(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    public_id = update.message.text.strip()
    usuario_id = update.effective_user.id

    # ========================================================
    # 🔎 BUSCAR CONTRATO
    # ========================================================
    with con() as x:
        prestamo = x.execute(
            """
            SELECT *
            FROM anuncios
            WHERE public_id=?
            AND estado IN ('COLATERAL_CONFIRMADO', 'LIQUIDABLE')
            """,
            (public_id,)
        ).fetchone()

    if not prestamo:
        await update.message.reply_text(
            "❌ No encontré ese contrato o "
            "todavía no tiene el collateral confirmado.\n\n"
            "Verifica el ID e inténtalo nuevamente."
        )
        return MOVER_CONTRATO

    # ========================================================
    # 🔐 AUTORIZACIÓN
    # SOLO EL ADMIN PUEDE MOVER FONDOS
    # ========================================================
    autorizado = usuario_id in {
        ADMIN_ID,
        prestamo["solicitante_id"],
    }

    if not autorizado:
        await update.message.reply_text(
            "❌ No perteneces a la operacion."
        )
        return ConversationHandler.END
    # ========================================================
    # 🚨 COMPROBACIÓN DEFENSIVA DE ANOMALÍA
    # ========================================================
    #
    # Este punto solo debería ser alcanzable si la lógica
    # anterior de autorización estuviera alterada o hubiera
    # un error lógico.
    #
    # Si por algún motivo el usuario NO es admin pero el flujo
    # continúa, registrar como CRITICAL.
    #
    if usuario_id not in {
    ADMIN_ID,
    prestamo["tomador_id"],
    prestamo["solicitante_id"],
}:
        await log_evento(
            context=context,
            accion="MOVER_FONDOS",
            public_id=public_id,
            usuario_id=usuario_id,
            autorizado=False,
            motivo="Usuario no autorizado consiguió superar la validación",
            resultado="ACCESO_A_MOVER_CONTRATO",
            severidad="CRITICAL"
        )

        await alertar_admin(
            context=context,
            accion="MOVER_FONDOS",
            public_id=public_id,
            usuario_id=usuario_id,
            motivo="Usuario no autorizado consiguió superar la validación",
            resultado="🚨 ANOMALÍA: ACCESO A MOVER FONDOS SIN AUTORIZACIÓN"
        )

        await update.message.reply_text(
            "❌ Operación bloqueada por seguridad."
        )
        return ConversationHandler.END

    # ========================================================
    # ✅ CONTINUAR
    # ========================================================
    context.user_data["mover_public_id"] = public_id

    await update.message.reply_text(
        f"✅ CONTRATO ENCONTRADO\n\n"
        f"🆔 Contrato:\n{public_id}\n\n"
        f"₿ Colateral:\n"
        f"{fmt(prestamo['deposito_sats'])} sats\n\n"
        f"🔗 TXID:\n{prestamo['collateral_txid']}\n\n"
        f"🔢 VOUT:\n{prestamo['collateral_vout']}\n\n"
        "Ahora introduce la dirección BTC Testnet "
        "de destino."
    )

    return MOVER_DIRECCION


async def mover_direccion(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    direccion = update.message.text.strip()
    usuario_id = update.effective_user.id

    # Obtener contrato de la sesión
    public_id = context.user_data.get(
        "mover_public_id"
    )

    if not public_id:
        await update.message.reply_text(
            "❌ No hay ningún contrato pendiente."
        )
        return ConversationHandler.END

    # Buscar contrato
    with con() as x:
        prestamo = x.execute(
            """
            SELECT *
            FROM anuncios
            WHERE public_id=?
            AND estado IN ('COLATERAL_CONFIRMADO', 'LIQUIDABLE')
            """,
            (public_id,)
        ).fetchone()

    if not prestamo:
        await update.message.reply_text(
            "❌ No encontré el contrato "
            "o ya no está disponible para mover."
        )
        return ConversationHandler.END

    # ==========================================================
    # 🔒 BLOQUEAR SOLO AL USUARIO SELECCIONADO POR EL ADMIN
    # ==========================================================

    usuario_bloqueado = prestamo["usuario_bloqueado_direccion"]

    if (
        usuario_bloqueado is not None
        and int(usuario_bloqueado) == usuario_id
    ):
        await update.message.reply_text(
            "❌ No puedes proporcionar la dirección BTC "
            "de este contrato."
        )

        context.user_data.clear()

        return ConversationHandler.END

    # ==========================================================
    # 🔎 VALIDAR FORMATO DE DIRECCIÓN TESTNET
    # ==========================================================

    if not (
        direccion.startswith("tb1")
        or direccion.startswith("m")
        or direccion.startswith("n")
        or direccion.startswith("2")
    ):
        await update.message.reply_text(
            "❌ La dirección no parece ser de Testnet.\n\n"
            "Introduce una dirección BTC Testnet válida."
        )
        return MOVER_DIRECCION

    # ==========================================================
    # 🔎 VALIDAR DIRECCIÓN CON BITCOIN CORE
    # ==========================================================

    try:
        resultado = await rpc_core(
            "validateaddress",
            [direccion]
        )

        if not resultado.get("isvalid"):
            await update.message.reply_text(
                "❌ Bitcoin Core rechazó la dirección.\n\n"
                "Introduce otra dirección Testnet."
            )
            return MOVER_DIRECCION

    except Exception as e:
        await update.message.reply_text(
            "❌ No pude validar la dirección con Bitcoin Core.\n\n"
            f"{str(e)[:200]}"
        )
        return MOVER_DIRECCION

    # ==========================================================
    # 💾 GUARDAR DIRECCIÓN EN LA SESIÓN
    # ==========================================================

    context.user_data["mover_direccion"] = direccion

    # ==========================================================
    # ⚠️ MOSTRAR CONFIRMACIÓN
    # ==========================================================

    await update.message.reply_text(
        f"📤 MOVIMIENTO DE FONDOS\n\n"
        f"🆔 Contrato:\n{public_id}\n\n"
        f"📍 Dirección destino:\n{direccion}\n\n"
        "⚠️ Verifica la dirección antes de continuar.\n\n"
        "Escribe CONFIRMAR para continuar."
    )

    return MOVER_CONFIRMAR

async def mover_confirmar(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    texto = update.message.text.strip().upper()

    if texto != "CONFIRMAR":
        await update.message.reply_text(
            "❌ Operación cancelada.\n\n"
            "Escribe /mover para comenzar nuevamente."
        )
        context.user_data.clear()
        return ConversationHandler.END

    # Recuperar datos de la conversación
    public_id = context.user_data.get("mover_public_id")
    direccion = context.user_data.get("mover_direccion")

    if not public_id or not direccion:
        await update.message.reply_text(
            "❌ Faltan datos de la operación.\n\n"
            "Escribe /mover para comenzar nuevamente."
        )
        context.user_data.clear()
        return ConversationHandler.END

    # Buscar el contrato
    with con() as x:
        prestamo = x.execute(
            """
            SELECT *
            FROM anuncios
            WHERE public_id=?
            AND estado IN ('COLATERAL_CONFIRMADO', 'LIQUIDABLE')
            """,
            (public_id,)
        ).fetchone()
        print("DEBUG public_id:", public_id)
        print("DEBUG prestamo:", dict(prestamo) if prestamo else None)

    # IMPORTANTE:
    # Si NO existe, aquí se detiene la función.
    if not prestamo:
        await update.message.reply_text(
            "❌ El contrato ya no está disponible "
            "o no tiene el collateral confirmado."
        )
        context.user_data.clear()
        return ConversationHandler.END

    # Recuperar datos del colateral
    txid = prestamo["collateral_txid"]
    vout = prestamo["collateral_vout"]
    sats = prestamo["deposito_sats"]
    witness_script = prestamo["witness_script"]

    # Verificar que tenemos todo lo necesario
    if (
        not txid
        or vout is None
        or not sats
        or not witness_script
    ):
        await update.message.reply_text(
            "❌ Faltan datos del colateral para crear la PSBT.\n\n"
            f"TXID: {'OK' if txid else 'FALTA'}\n"
            f"VOUT: {'OK' if vout is not None else 'FALTA'}\n"
            f"SATS: {'OK' if sats else 'FALTA'}\n"
            f"Witness Script: {'OK' if witness_script else 'FALTA'}"
        )
        context.user_data.clear()
        return ConversationHandler.END

    # Validar dirección de destino
    if not direccion.lower().startswith("tb1"):
        await update.message.reply_text(
            "❌ Dirección inválida.\n\n"
            "Para esta prueba debes utilizar "
            "una dirección Bitcoin Testnet que comience por tb1."
        )
        context.user_data.clear()
        return ConversationHandler.END

    # Crear PSBT
    await update.message.reply_text(
        "⏳ Creando PSBT...\n\n"
        "Los fondos todavía NO se han movido."
    )

    try:
        print("========== DATOS PARA CREAR PSBT ==========")
        print("TXID:", txid)
        print("VOUT:", vout)
        print("SATS:", sats)
        print("FEE:", 100)
        print("==========================================")
        resultado = await bitcoin_testnet.crear_psbt(
            rpc_core,
            txid,
            vout,
            sats,
            witness_script,
            direccion,
            100
        )

    except Exception as e:
        await update.message.reply_text(
            "❌ No se pudo crear la PSBT.\n\n"
            f"Detalle: {str(e)[:300]}"
        )
        context.user_data.clear()
        return ConversationHandler.END

    psbt = resultado["psbt"]

    # Guardar PSBT y dirección
    with con() as x:
        x.execute(
            """
            UPDATE anuncios
            SET
                direccion_destino=?,
                psbt=?,
                estado='PSBT_CREADA'
            WHERE public_id=?
            """,
            (
                direccion,
                psbt,
                public_id
            )
        )
        x.commit()

    await update.message.reply_text(
        f"✅ PSBT CREADA\n\n"
        f"🆔 Contrato:\n{public_id}\n\n"
        f"📍 Destino:\n{direccion}\n\n"
        f"🔗 TXID entrada:\n{txid}\n\n"
        f"🔢 VOUT:\n{vout}\n\n"
        f"₿ Entrada:\n{fmt(sats)} sats\n\n"
        "🔐 Estado: PSBT_CREADA\n\n"
        "⏳ La PSBT todavía NO está firmada.\n"
        "⏳ Los fondos todavía NO se han movido.\n\n"
        "➡️ Siguiente paso: solicitar las 2 firmas."
    )

        # Identificar quién solicitó el movimiento
    usuario_id = update.effective_user.id

    if usuario_id == prestamo["solicitante_id"]:
        contraparte_id = prestamo["tomador_id"]
        quien_mueve = "PRESTAMISTA"

    elif usuario_id == prestamo["tomador_id"]:
        contraparte_id = prestamo["solicitante_id"]
        quien_mueve = "PRESTATARIO"

    elif usuario_id == ADMIN_ID:
        contraparte_id = None
        quien_mueve = "ADMIN"

    else:
        await update.message.reply_text(
            "❌ No participas en este contrato."
        )
        context.user_data.clear()
        return ConversationHandler.END

    # Avisar a la contraparte
    await context.bot.send_message(
        chat_id=contraparte_id,
        text=(
            "🔔 SOLICITUD PARA MOVER FONDOS\n\n"
            f"🆔 Contrato:\n{public_id}\n\n"
            f"👤 SOLICITÓ EL MOVIMIENTO:\n{quien_mueve}\n\n"
            "📤 LOS FONDOS SERÁN ENVIADOS A:\n"
            f"{direccion}\n\n"
            "⚠️ VERIFICA LA DIRECCIÓN ANTES DE FIRMAR.\n\n"
            "Si la dirección es correcta:\n"
            "➡️ Usa /firmar\n"
            "➡️ Escribe el ID del contrato.\n\n"
            "❌ Si la dirección no coincide, NO FIRMES."
        )
    )

    context.user_data.clear()

    return ConversationHandler.END
    
async def revisar_depositos_job(context):
    try:
        # 1. Expirar depósitos pendientes después de 30 minutos
        with con() as x:
            prestamos_expirados = x.execute(
                """
                SELECT *
                FROM anuncios
                WHERE estado='DEPOSITO_BTC_PENDIENTE'
                AND collateral_txid IS NULL
                AND datetime(fecha) < datetime('now', '-80 minutes')
                """
            ).fetchall()

        # Marcar como expirados y avisar
        for a in prestamos_expirados:

            with con() as x:
                resultado = x.execute(
                    """
                    UPDATE anuncios
                    SET estado='DEPOSITO_EXPIRADO'
                    WHERE public_id=?
                    AND estado='DEPOSITO_BTC_PENDIENTE'
                    AND collateral_txid IS NULL
                    """,
                    (a["public_id"],)
                )

            # Evitar mensajes duplicados
            if resultado.rowcount == 0:
                continue

            print(f"🗑️ Operación expirada: {a['public_id']}")

            mensaje_expirado = f"""⏰ OPERACIÓN EXPIRADA

🆔 Contrato:
{a['public_id']}

⚠️ No se recibió el depósito de BTC
dentro del plazo de 80 minutos.

📌 Estado:
DEPOSITO_EXPIRADO
"""

            # Avisar al prestamista
            try:
                await context.bot.send_message(
                    chat_id=a["solicitante_id"],
                    text=mensaje_expirado
                )
            except Exception as e:
                print(
                    f"❌ No se pudo avisar al prestamista "
                    f"{a['public_id']}: {e}"
                )

            # Avisar al tomador
            try:
                await context.bot.send_message(
                    chat_id=a["tomador_id"],
                    text=mensaje_expirado
                )
            except Exception as e:
                print(
                    f"❌ No se pudo avisar al tomador "
                    f"{a['public_id']}: {e}"
                )

        # 2. Buscar depósitos recientes
        with con() as x:
            prestamos = x.execute(
                """
                SELECT *
                FROM anuncios
                WHERE estado='DEPOSITO_BTC_PENDIENTE'
                AND collateral_txid IS NULL
                AND datetime(fecha) >= datetime('now', '-2000 minutes')
                AND multisig_address IS NOT NULL
                AND deposito_sats IS NOT NULL
                ORDER BY id DESC
                LIMIT 10
                """
            ).fetchall()

        if not prestamos:
                      return

        print(f"🔎 Depósitos pendientes: {len(prestamos)}")

        # 3. Revisar cada préstamo
        for a in prestamos:
            print("")
            print("========================================")
            print("🔎 REVISANDO PRÉSTAMO")
            print("🆔 ID:", a["public_id"])
            print("📍 Dirección:", a["multisig_address"])
            print("₿ Colateral:", a["deposito_sats"], "sats")
            print("📅 Creado:", a["fecha"])
            print("⏳ Vencimiento:", a["vencimiento"])
            print("========================================")

            try:
                deposito = await bitcoin_testnet.verificar_deposito(
                    rpc_core,
                    a["multisig_address"],
                    a["deposito_sats"]
                )

            except Exception as e:
                print("❌ Error consultando depósito:", e)
                continue

            if not deposito:
                print("⏳ DEPÓSITO NO ENCONTRADO")
                continue

            print("")
            print("🎉 DEPÓSITO DETECTADO")
            print("🆔 ID:", a["public_id"])
            print("🔗 TXID:", deposito["txid"])
            print("🔢 VOUT:", deposito["vout"])
            print("₿ SATS:", deposito["sats"])

            # 4. Guardar depósito
            with con() as x:
                resultado = x.execute(
                    """
                    UPDATE anuncios
                    SET
                        collateral_txid=?,
                        collateral_vout=?,
                        estado='COLATERAL_CONFIRMADO'
                    WHERE public_id=?
                      AND estado='DEPOSITO_BTC_PENDIENTE'
                      AND collateral_txid IS NULL
                    """,
                    (
                        deposito["txid"],
                        deposito["vout"],
                        a["public_id"]
                    )
                )

            # Evitar doble procesamiento por jobs solapados
            if resultado.rowcount != 1:
                print(
                    f"⚠️ Depósito ya procesado por otra ejecución: "
                    f"{a['public_id']}"
                )
                continue

            # 5. Avisar al prestamista
            await context.bot.send_message(
                a["solicitante_id"],
                f"""✅ COLATERAL CONFIRMADO

🆔 Contrato:
{a['public_id']}

👤 Tomador:
@{a['tomador_username']}

₿ Colateral:
{a['deposito_sats'] / 100_000_000:.8f} BTC

🔗 TXID:
{deposito['txid']}

🔢 VOUT:
{deposito['vout']}

📌 Estado:
COLATERAL_CONFIRMADO
"""
            )

            # 6. Avisar al tomador
            await context.bot.send_message(
                a["tomador_id"],
                f"""✅ DEPÓSITO DETECTADO

🆔 Contrato:
{a['public_id']}

👤 Prestamista:
@{a['solicitante_username']}

₿ Colateral:
{a['deposito_sats'] / 100_000_000:.8f} BTC

💰 Monto a enviar:
{fmt(a['monto_final'] or 0)} {a['moneda']}

💳 Método de pago:
{a['metodo_pago']}

👉 Envía el dinero a tu contraparte .

🔗 TXID:
{deposito['txid']}

🔢 VOUT:
{deposito['vout']}

📌 Estado:
COLATERAL_CONFIRMADO
"""
            )

    except Exception as e:       
        print("❌ ERROR GENERAL REVISANDO DEPÓSITOS:", e)

async def revisar_ltv_job(context):
    print("🔎 REVISANDO LTV...")

    ahora = datetime.now(timezone.utc)

    with con() as c:
        prestamos = c.execute("""
            SELECT *
            FROM anuncios
            WHERE estado='COLATERAL_CONFIRMADO'
            AND collateral_txid IS NOT NULL
              AND deposito_sats IS NOT NULL
              AND monto_final IS NOT NULL
        """).fetchall()

    for a in prestamos:
        try:
            precio, _ = await yadio_sats(
                a["monto_final"],
                a["moneda"]
            )

            ltv = calcular_ltv(
                a["monto_final"],
                a["deposito_sats"],
                precio
            )

            print(
                f"📊 {a['public_id']} | "
                f"LTV ACTUAL: {ltv:.2f}% | "
                f"LTV MÁXIMO: {LTV_MAXIMO}%"
            )

            with con() as c:

                # =========================
                # LTV NORMAL
                # =========================

                if False:

                    c.execute("""
                        UPDATE anuncios
                        SET
                            ltv_actual=?,
                            gracia_inicio=NULL,
                            gracia_hasta=NULL,
                            estado_liquidacion='NORMAL'
                        WHERE public_id=?
                    """, (
                        str(ltv),
                        a["public_id"]
                    ))

                # =========================
                # LTV EN O SOBRE EL LÍMITE
                # =========================

                else:

                    # =========================
                    # INICIAR GRACIA
                    # =========================

                    if not a["gracia_inicio"]:

                        gracia_inicio = ahora

                        gracia_hasta = ahora + timedelta(
                            minutes=1
                        )

                        c.execute("""
                            UPDATE anuncios
                            SET
                                ltv_actual=?,
                                gracia_inicio=?,
                                gracia_hasta=?,
                                estado_liquidacion='EN_GRACIA'
                            WHERE public_id=?
                        """, (
                            str(ltv),
                            gracia_inicio.isoformat(),
                            gracia_hasta.isoformat(),
                            a["public_id"]
                        ))

                        print(
                            f"⚠️ {a['public_id']} "
                            f"LTV {ltv:.2f}% → "
                            f"EN_GRACIA hasta "
                            f"{gracia_hasta.isoformat()}"
                        )

                        mensaje = f"""⚠️ ALERTA DE LTV

🆔 Contrato:
{a['public_id']}

📊 LTV actual:
{ltv:.2f}%

🚨 Límite:
{LTV_MAXIMO:.2f}%

⏳ Período de gracia:
{DIAS_GRACIA} días

📅 La gracia termina:
{gracia_hasta.strftime('%Y-%m-%d %H:%M UTC')}

Durante este período el LTV seguirá siendo monitoreado.

Si el LTV vuelve a estar por debajo de {LTV_MAXIMO:.2f}%, la alerta se cancelará.
"""

                        # Avisar al prestamista
                        try:
                            await context.bot.send_message(
                                chat_id=a["solicitante_id"],
                                text=mensaje
                            )
                        except Exception as e:
                            print(
                                f"❌ No se pudo avisar al prestamista "
                                f"{a['public_id']}: {e}"
                            )

                        # Avisar al tomador
                        try:
                            await context.bot.send_message(
                                chat_id=a["tomador_id"],
                                text=mensaje
                            )
                        except Exception as e:
                            print(
                                f"❌ No se pudo avisar al tomador "
                                f"{a['public_id']}: {e}"
                            )

                    # =========================
                    # YA ESTÁ EN GRACIA
                    # =========================

                    else:

                        gracia_hasta = datetime.fromisoformat(
                            a["gracia_hasta"]
                        )

                        # =========================
                        # GRACIA TERMINADA
                        # =========================

                        if ahora >= gracia_hasta and a["estado"] not in ("LIQUIDABLE", "LIQUIDADO"):

                            c.execute("""
                                UPDATE anuncios
                                SET
                                    ltv_actual=?,
                                    estado='LIQUIDABLE',
                                    estado_liquidacion='LIQUIDABLE'
                                WHERE public_id=?
                            """, (
                                str(ltv),
                                a["public_id"]
                            ))
                            c.commit()

                            print(
                                f"🚨 {a['public_id']} "
                                f"LTV {ltv:.2f}% → LIQUIDABLE"
                            )

                            mensaje_liquidable = f"""🚨 PERÍODO DE GRACIA TERMINADO

🆔 Contrato:
{a['public_id']}

📊 LTV actual:
{ltv:.2f}%

🚨 Límite:
{LTV_MAXIMO:.2f}%

⏰ El período de gracia de {DIAS_GRACIA} días ha terminado.

📌 Estado:
LIQUIDABLE
"""

                            # Avisar al prestamista
                            try:
                                await context.bot.send_message(
                                    chat_id=a["solicitante_id"],
                                    text=mensaje_liquidable
                                )
                            except Exception as e:
                                print(
                                    f"❌ No se pudo avisar al prestamista "
                                    f"{a['public_id']}: {e}"
                                )

                            # Avisar al tomador
                            try:
                                await context.bot.send_message(
                                    chat_id=a["tomador_id"],
                                    text=mensaje_liquidable
                                )
                            except Exception as e:
                                print(
                                    f"❌ No se pudo avisar al tomador "
                                    f"{a['public_id']}: {e}"
                                )

                        # =========================
                        # SIGUE EN GRACIA
                        # =========================

                        else:

                            c.execute("""
                                UPDATE anuncios
                                SET ltv_actual=?
                                WHERE public_id=?
                            """, (
                                str(ltv),
                                a["public_id"]
                            ))

        except Exception as e:

            print(
                f"❌ Error revisando LTV "
                f"{a['public_id']}: {e}"
            )

async def firmar_contrato(update, context):
    public_id = update.message.text.strip()
    usuario_id = update.effective_user.id

    with con() as x:
        prestamo = x.execute(
            """
            SELECT *
            FROM anuncios
            WHERE public_id=?
            AND estado='PSBT_CREADA'
            """,
            (public_id,)
        ).fetchone()

    if not prestamo:
        await update.message.reply_text(
            "❌ No encontré una PSBT pendiente para ese contrato.\n\n"
            "Verifica el ID e inténtalo nuevamente."
        )
        return FIRMAR_CONTRATO
    print("=== AUTORIZACIÓN FIRMA ===")
    print("usuario_id:", usuario_id)
    print("solicitante_id:", prestamo["solicitante_id"])
    print("tomador_id:", prestamo["tomador_id"])
    print("ADMIN_ID:", ADMIN_ID)
    print("==========================")
    if usuario_id not in (
        prestamo["solicitante_id"],
        prestamo["tomador_id"],
        ADMIN_ID
    ):
        
        await update.message.reply_text(
            "❌ No estás autorizado para firmar este contrato."
        )
        return ConversationHandler.END

    # Verificar que exista una dirección BTC guardada
    direccion = prestamo["direccion_destino"]

    if not direccion:
        await update.message.reply_text(
            "❌ Este contrato no tiene una dirección BTC de destino guardada.\n\n"
            "Por seguridad, no se puede firmar."
        )
        return ConversationHandler.END

    # Datos de quién registró la dirección
    usuario_direccion = (
        prestamo["direccion_destino_username"]
        or "Sin username"
    )

    rol_direccion = (
        prestamo["direccion_destino_rol"]
        or "ROL NO REGISTRADO"
    )

    # Guardar contrato seleccionado
    context.user_data["firmar_public_id"] = public_id

    # Identificar rol
    if usuario_id == prestamo["solicitante_id"]:
        rol = "PRESTAMISTA"

    elif usuario_id == prestamo["tomador_id"]:
        rol = "PRESTATARIO"

    elif usuario_id == ADMIN_ID:
        rol = "ADMIN"

    else:
        await update.message.reply_text(
            "❌ No estás autorizado para firmar este contrato."
        )
        return ConversationHandler.END
     # Obtener usuario de Telegram
    usuario = update.effective_user

    username = (
    f"@{usuario.username}"
    if usuario.username
    else usuario.full_name
)
    # Mostrar información antes de firmar
    await update.message.reply_text(
        f"🔐 FIRMAR CONTRATO\n\n"
        f"🆔 Contrato:\n"
        f"{prestamo['public_id']}\n\n"

        f"₿ DIRECCIÓN BTC DE DESTINO\n"
        f"{direccion}\n\n"

        f"👤 REGISTRADA POR\n"
        f"{username}\n\n"

        f"✍️ TU ROL AL FIRMAR\n"
        f"{rol}\n\n"

        f"💰 MONTO\n"
        f"{fmt(prestamo['monto_final'] or 0)} "
        f"{prestamo['moneda']}\n\n"

        f"⚠️ VERIFICA ANTES DE FIRMAR\n"
        f"Comprueba que la dirección BTC, el usuario "
        f"y el rol sean correctos.\n\n"

        f"Si algo no coincide, NO FIRMES.\n\n"

        f"Para continuar, escribe:\n"
        f"FIRMAR"
    )

    return RECIBIR_FIRMA

async def recibir_firma(update, context):
    public_id = context.user_data.get("firmar_public_id")
    usuario_id = update.effective_user.id

    if not public_id:
        await update.message.reply_text(
            "❌ No hay ningún contrato pendiente de firma."
        )
        return ConversationHandler.END

    # Solo aceptar la palabra FIRMAR
    texto = update.message.text.strip().upper()

    if texto != "FIRMAR":
        await update.message.reply_text(
            "❌ Operación cancelada.\n\n"
            "Debes escribir FIRMAR para continuar."
        )
        return ConversationHandler.END

    # Buscar contrato
    with con() as x:
        prestamo = x.execute(
            """
            SELECT *
            FROM anuncios
            WHERE public_id=?
            AND estado='PSBT_CREADA'
            """,
            (public_id,)
        ).fetchone()

    if not prestamo:
        await update.message.reply_text(
            "❌ No encontré una PSBT pendiente para ese contrato."
        )
        return ConversationHandler.END

    # 🔐 COMPROBAR AUTORIZACIÓN ANTES DE FIRMAR
    autorizado, motivo_autorizacion = autorizado_para_contrato(
        prestamo,
        usuario_id,
        permitir_admin=True
    )

    if not autorizado:
        await log_evento(
            context=context,
            accion="FIRMAR",
            public_id=prestamo["public_id"],
            usuario_id=usuario_id,
            autorizado=False,
            motivo=motivo_autorizacion,
            resultado="FIRMA_RECHAZADA_SIN_AUTORIZACION",
            severidad="CRITICAL"
        )

        await alertar_admin(
            context=context,
            accion="FIRMAR",
            public_id=prestamo["public_id"],
            usuario_id=usuario_id,
            motivo=motivo_autorizacion,
            resultado="🚨 INTENTO DE FIRMA SIN AUTORIZACIÓN"
        )

        await update.message.reply_text(
            "❌ No estás autorizado para firmar este contrato."
        )

        return ConversationHandler.END

    try:
        # Determinar quién está firmando
        if usuario_id == prestamo["solicitante_id"]:
            privkey = prestamo["prestamista_privkey"]
            pubkey = prestamo["prestamista_pubkey"]
            columna_firma = "firma_prestamista"
            rol = "PRESTAMISTA"

        elif usuario_id == prestamo["tomador_id"]:
            privkey = prestamo["prestatario_privkey"]
            pubkey = prestamo["prestatario_pubkey"]
            columna_firma = "firma_prestatario"
            rol = "PRESTATARIO"

        elif usuario_id == ADMIN_ID and permitir_admin:
            privkey = prestamo["admin_privkey"]
            pubkey = prestamo["admin_pubkey"]
            columna_firma = "firma_admin"
            rol = "ADMIN"

        else:
            await update.message.reply_text(
                "❌ No estás autorizado para firmar este contrato."
            )
            return ConversationHandler.END

        # Comprobar que existan las claves
        if not privkey or not pubkey:
            print("ROL:", rol)
            print("PUBKEY EXISTE:", bool(pubkey))
            print("PRIVKEY EXISTE:", bool(privkey))

            raise ValueError(
                f"No existe la clave del {rol}."
            )

        # Obtener PSBT actual
        psbt_actual = prestamo["psbt"]

        # Firmar PSBT
        resultado = await bitcoin_testnet.firmar_psbt(
            psbt_actual,
            privkey,
            pubkey
        )

        psbt_nueva = resultado["psbt"]

        # Guardar firma y PSBT actualizada
        with con() as x:
            x.execute(
                f"""
                UPDATE anuncios
                SET psbt=?,
                    {columna_firma}=?
                WHERE public_id=?
                """,
                (
                    psbt_nueva,
                    "FIRMADA",
                    public_id
                )
            )
            x.commit()

        # Volver a consultar el contrato
        with con() as x:
            actualizado = x.execute(
                """
                SELECT *
                FROM anuncios
                WHERE public_id=?
                """,
                (public_id,)
            ).fetchone()

        firma1 = actualizado["firma_prestamista"]
        firma2 = actualizado["firma_prestatario"]
        firma3 = actualizado["firma_admin"]

        # Contar firmas
        firmas = sum(
            bool(f)
            for f in (firma1, firma2, firma3)
        )

        # Todavía falta una firma
        if firmas < 2:
            username = update.effective_user.username or str(usuario_id)

            await update.message.reply_text(
                f"✍️ FIRMA AGREGADA\n\n"
                f"🆔 Contrato:\n"
                f"{public_id}\n\n"
                f"₿ Dirección de destino:\n"
                f"{actualizado['direccion_destino']}\n\n"
                f"👤 Firmante: @{username}\n"
                f"🎭 Rol: {rol}\n\n"
                f"🔐 Firmas registradas: {firmas}/3\n\n"
                f"⏳ Se necesitan 2 de 3 firmas.\n\n"
                f"⚠️ La transacción todavía NO fue transmitida."
            )

            return ConversationHandler.END

        # Ya existen 2 o más firmas
        await update.message.reply_text(
            "🔐 Hay 2 o más firmas registradas.\n\n"
            "⏳ Finalizando transacción..."
        )

        # 🔐 ÚLTIMA COMPROBACIÓN DE SEGURIDAD ANTES DE TRANSMITIR
        autorizado, motivo_autorizacion = autorizado_para_contrato(
            actualizado,
            usuario_id,
            permitir_admin=True
        )

        if not autorizado:
            await log_evento(
                context=context,
                accion="TRANSMITIR",
                public_id=actualizado["public_id"],
                usuario_id=usuario_id,
                autorizado=False,
                motivo=motivo_autorizacion,
                resultado="TRANSMISION_RECHAZADA_SIN_AUTORIZACION",
                severidad="CRITICAL"
            )

            await alertar_admin(
                context=context,
                accion="TRANSMITIR",
                public_id=actualizado["public_id"],
                usuario_id=usuario_id,
                motivo=motivo_autorizacion,
                resultado="🚨 INTENTO DE TRANSMISIÓN SIN AUTORIZACIÓN"
            )

            await update.message.reply_text(
                "❌ No autorizado para transmitir este contrato."
            )

            return ConversationHandler.END

        # SOLO DESPUÉS DE PASAR TODAS LAS AUTORIZACIONES
        resultado_tx = await bitcoin_testnet.finalizar_y_transmitir(
            rpc_core,
            psbt_nueva
        )

        txid_final = resultado_tx["txid"]

        with con() as x:
            x.execute(
                """
                UPDATE anuncios
                SET estado='TRANSMITIDA'
                WHERE public_id=?
                """,
                (public_id,)
            )
            x.commit()

        await update.message.reply_text(
            "✅ TRANSACCIÓN TRANSMITIDA\n\n"
            f"🆔 Contrato:\n"
            f"{public_id}\n\n"
            f"🔗 TXID:\n"
            f"{txid_final}\n\n"
            "La transacción fue enviada a Bitcoin Core."
        )

        return ConversationHandler.END

    except Exception as e:
        print(
            "ERROR FIRMAR/TRANSMITIR:",
            repr(e)
        )

        await update.message.reply_text(
            "❌ Error al firmar o transmitir.\n\n"
            f"Detalle: {e}"
        )

        return ConversationHandler.END
async def mover(update: Update, context: ContextTypes.DEFAULT_TYPE):

    await update.message.reply_text(
        "₿ MOVIMIENTO DE FONDOS\n\n"
        "Escribe el ID del contrato que quieres mover.\n\n"
        "Ejemplo:\n"
        "ABC123\n\n"
        "Escribe /cancelar para cancelar."
    )

    return MOVER_CONTRATO
async def firmar(update: Update, context: ContextTypes.DEFAULT_TYPE):

    await update.message.reply_text(
        "✍️ FIRMAR CONTRATO\n\n"
        "Escribe el ID del contrato.\n\n"
        "Ejemplo:\n"
        "PRE-20260830-08FE9C9BD7C44644A9B07E63C3ABDB34\n\n"
        "⚠️ Firmar NO mueve los fondos."
    )

    return FIRMAR_CONTRATO


async def admin_reiniciar_psbt(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    admin_id = update.effective_user.id

    if admin_id != ADMIN_ID:
        await update.message.reply_text(
            "❌ No autorizado."
        )
        return ConversationHandler.END

    partes = update.message.text.strip().split()

    if len(partes) != 2:
        await update.message.reply_text(
            "Uso:\n"
            "/reiniciarpsbt PUBLIC_ID"
        )
        return ConversationHandler.END

    public_id = partes[1]

    with con() as x:
        prestamo = x.execute(
            """
            SELECT *
            FROM anuncios
            WHERE public_id=?
            """,
            (public_id,)
        ).fetchone()

        if not prestamo:
            await update.message.reply_text(
                "❌ No encontré ese contrato."
            )
            return ConversationHandler.END
    estado_actual = x.execute(
    """
    SELECT estado
    FROM anuncios
    WHERE public_id=?
    """,
    (public_id,)
    ).fetchone()["estado"]
    x.execute(
            """
            UPDATE anuncios
            SET
                psbt=NULL,
                firma_prestamista=NULL,
                firma_prestatario=NULL,
                firma_admin=NULL,
                direccion_destino=NULL,
                estado=?
            WHERE public_id=?
            """,
            (estado_actual,public_id)
        )

    x.commit()

    await update.message.reply_text(
        "🔄 PSBT REINICIADA\n\n"
        f"🆔 Contrato: {public_id}\n\n"
        "La dirección anterior fue eliminada.\n"
        "Las firmas anteriores fueron eliminadas.\n"
        "El contrato volvió a COLATERAL_CONFIRMADO.\n\n"
        "🔒 El usuario bloqueado para proporcionar "
        "la dirección continúa bloqueado."
    )

    return ConversationHandler.END
async def error_handler(update, context):
    logger.exception(
        "Error procesando actualización",
        exc_info=context.error
    )

    if update and update.effective_message:
        try:
            await update.effective_message.reply_text(
                "No pude procesar esa solicitud 😅. "
                "Usa /ayuda o /start para ver las opciones."
            )
        except Exception:
            pass
async def mensaje_no_reconocido(update, context):
    await update.effective_message.reply_text(
        "No entendí esa solicitud 😅\n\n"
        "Usa /start para ver las opciones disponibles."
    )

def main():
    crear_db()

    app = (
        Application.builder()
        .token(TOKEN)
        .connect_timeout(30)
        .read_timeout(30)
        .write_timeout(30)
        .pool_timeout(30)
        .build()
    )

    pub = ConversationHandler(
    entry_points=[
        CommandHandler("prestamo", iniciar),
        CommandHandler("ofrecer_prestamo",iniciar),
    ],

    states={
        MONEDA: [MessageHandler(filters.TEXT & ~filters.COMMAND, moneda)],
        MONTO: [MessageHandler(filters.TEXT & ~filters.COMMAND, rango)],
        PAGO: [MessageHandler(filters.TEXT & ~filters.COMMAND, pago)],
        INTERES: [MessageHandler(filters.TEXT & ~filters.COMMAND, interes)],
        VENCE: [MessageHandler(filters.TEXT & ~filters.COMMAND, publicar)],
    },

    fallbacks=[
        CommandHandler("cancelar", cancelar)
    ]

)

    take = ConversationHandler(
    entry_points=[
        CallbackQueryHandler(
            tomar,
            pattern=r"^tomar:"
        )
    ],
    per_chat=False,
    states={
        MONTO_TOMADOR: [
            MessageHandler(
                filters.TEXT & ~filters.COMMAND,
                monto_tomador
            )
        ]
    },
    fallbacks=[
        CommandHandler("cancelar", cancelar)
    ]
)
    per_chat=False,

    mover_conv = ConversationHandler(
        entry_points=[
            CommandHandler("mover", mover)
        ],
        states={
            MOVER_CONTRATO: [
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND,
                    mover_contrato
                )
            ],
            MOVER_DIRECCION: [
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND,
                    mover_direccion
                )
            ],
            MOVER_CONFIRMAR: [
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND,
                    mover_confirmar
                )
            ],
        },
        fallbacks=[
            CommandHandler("cancelar", cancelar)
        ]
    )


    firmar_conv = ConversationHandler(
        entry_points=[
            CommandHandler("firmar", firmar)
        ],
        states={
    FIRMAR_CONTRATO: [
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            firmar_contrato
        )
    ],

    RECIBIR_FIRMA: [
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            recibir_firma
        )
    ],
},
        
        fallbacks=[
            CommandHandler("cancelar", cancelar)
        ]
    )


    app.add_handler(
        CommandHandler("start", start)
    )

    app.add_handler(
        CommandHandler("nodo", nodo)
    )

    app.add_handler(
        CommandHandler("node", nodo)
    )

    app.add_handler(
        CommandHandler("mis_anuncios", mis_anuncios)
    )
    app.add_handler(
    CommandHandler("reiniciarpsbt", admin_reiniciar_psbt)
)

    app.add_handler(
        CommandHandler("mis_tomas", mis_tomas)
    )
    app.add_handler(CommandHandler("disputa", disputa))


    app.add_handler(pub)
    app.add_handler(take)
    app.add_handler(mover_conv)
    app.add_handler(firmar_conv)
    app.add_handler(
    MessageHandler(
        filters.TEXT & ~filters.COMMAND,
        mensaje_no_reconocido
    )
)
    app.add_error_handler(error_handler)
    app.job_queue.run_repeating(
        revisar_depositos_job,
        interval=30,
        first=10
    )
    app.job_queue.run_repeating(
    revisar_ltv_job,
    interval=300,
    first=30
)

    app.add_error_handler(error_handler)

    app.run_polling()


if __name__ == "__main__":
    main()
