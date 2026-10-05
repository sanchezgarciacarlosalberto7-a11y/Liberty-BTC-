import sys
print("PYTHON bitcoin_testnet:", sys.executable)

from coincurve import PrivateKey

try:
    PrivateKey()
    print("COINCURVE bitcoin_testnet: OK")
except Exception as e:
    print("COINCURVE bitcoin_testnet: ERROR:", repr(e))

from bitcointx.core import (
    COutPoint,
    CMutableTransaction,
    CMutableTxIn,
    CMutableTxOut,
    lx,
)
from bitcointx.core.script import (
    CScript,
    SIGHASH_ALL,
    SIGVERSION_WITNESS_V0,
)

import bitcointx.core.secp256k1 as secp256k1

print("SECP256K1 BITCOINTX: OK")

from bitcointx.core.psbt import PartiallySignedTransaction
from bitcointx.wallet import P2WSHBitcoinTestnetAddress
from decimal import Decimal
from bitcointx.core.key import CPubKey
from bitcointx.core import CTxIn, COutPoint
from coincurve import PrivateKey
from bitcointx.core.psbt import (
    PartiallySignedTransaction,
    PSBT_Input,
    PSBT_Output
)

async def verificar_depositos(rpc, solicitudes, altura_inicio=None, altura_fin=None):
    """
    Detecta depósitos P2WSH directamente en los bloques recientes.

    Ya NO utiliza scantxoutset, porque en este nodo puede tardar
    más de 120 segundos y provocar timeout.

    Para cada solicitud:
      1. Obtiene el scriptPubKey correspondiente a la dirección.
      2. Revisa los bloques recientes.
      3. Busca una salida con ese scriptPubKey.
      4. Comprueba que el monto sea exactamente el esperado.
      5. Comprueba que el UTXO siga sin gastar.

    Devuelve:
        {
            public_id: {
                "txid": "...",
                "vout": 0,
                "sats": 123456,
                "height": ...,
                "confirmaciones": ...
            }
        }
    """

    if not solicitudes:
        return {}

    # ============================================================
    # 1. Obtener scriptPubKey de cada dirección
    # ============================================================

    por_script = {}

    for solicitud in solicitudes:
        direccion = solicitud["direccion"]

        try:
            info = await rpc(
                "validateaddress",
                [direccion]
            )
        except Exception as e:
            print(
                f"❌ Error validando dirección "
                f"{direccion}: {e}"
            )
            continue

        if not info.get("isvalid"):
            print(
                f"❌ Dirección inválida: {direccion}"
            )
            continue

        script_pubkey = info.get("scriptPubKey")

        if not script_pubkey:
            print(
                f"❌ La dirección no tiene scriptPubKey: "
                f"{direccion}"
            )
            continue

        por_script[script_pubkey.lower()] = solicitud

    if not por_script:
        return {}

    # ============================================================
    # 2. Obtener altura actual
    # ============================================================

    try:
        altura_actual = int(
            await rpc("getblockcount")
        )
    except Exception as e:
        print(
            f"❌ Error obteniendo altura blockchain: {e}"
        )
        return {}

    # Si el llamador no proporciona un rango,
    # mantenemos el comportamiento anterior: últimos 12 bloques.
    if altura_inicio is None:
        BLOQUES_A_REVISAR = 12
        altura_inicio = max(
            0,
            altura_actual - BLOQUES_A_REVISAR + 1
        )

    if altura_fin is None:
        altura_fin = altura_actual

    altura_inicio = max(0, int(altura_inicio))
    altura_fin = min(int(altura_fin), altura_actual)

    if altura_inicio > altura_fin:
        return {}

    encontrados = {}

    # ============================================================
    # 3. Recorrer bloques recientes
    # ============================================================

    for altura in range(
        altura_inicio,
        altura_fin + 1
    ):

        try:
            blockhash = await rpc(
                "getblockhash",
                [altura]
            )

            bloque = await rpc(
                "getblock",
                [blockhash, 2]
            )

        except Exception as e:
            print(
                f"❌ Error leyendo bloque {altura}: {e}"
            )
            continue

        for tx in bloque.get("tx", []):

            txid = tx.get("txid")

            if not txid:
                continue

            for vout in tx.get("vout", []):

                indice = int(vout.get("n", -1))

                script_pubkey = (
                    vout
                    .get("scriptPubKey", {})
                    .get("hex", "")
                    .lower()
                )

                if not script_pubkey:
                    continue

                solicitud = por_script.get(
                    script_pubkey
                )

                if not solicitud:
                    continue

                # ==============================================
                # 4. Comprobar monto exacto
                # ==============================================

                try:
                    sats = int(
                        Decimal(
                            str(vout["value"])
                        ) * 100_000_000
                    )
                except Exception:
                    continue

                sats_requeridos = int(
                    solicitud["sats_requeridos"]
                )

                if sats != sats_requeridos:
                    print(
                        f"⚠️ TX encontrada pero monto incorrecto: "
                        f"{txid}:{indice} "
                        f"{sats} sats != "
                        f"{sats_requeridos} sats"
                    )
                    continue

                # ==============================================
                # 5. Confirmar que el UTXO sigue sin gastar
                # ==============================================

                try:
                    utxo = await rpc(
                        "gettxout",
                        [
                            txid,
                            indice,
                            True
                        ]
                    )
                except Exception as e:
                    print(
                        f"⚠️ No se pudo verificar UTXO "
                        f"{txid}:{indice}: {e}"
                    )
                    continue

                if not utxo:
                    print(
                        f"⚠️ Salida encontrada pero ya no "
                        f"está disponible: {txid}:{indice}"
                    )
                    continue

                confirmaciones = int(
                    utxo.get("confirmations", 0)
                )

                print(
                    "✅ DEPÓSITO BTC DETECTADO"
                )
                print(
                    f"   Public ID: "
                    f"{solicitud['public_id']}"
                )
                print(
                    f"   TXID: {txid}"
                )
                print(
                    f"   VOUT: {indice}"
                )
                print(
                    f"   SATS: {sats}"
                )
                print(
                    f"   BLOQUE: {altura}"
                )
                print(
                    f"   CONFIRMACIONES: "
                    f"{confirmaciones}"
                )

                encontrados[
                    solicitud["public_id"]
                ] = {
                    "txid": txid,
                    "vout": indice,
                    "sats": sats,
                    "height": altura,
                    "confirmaciones": confirmaciones
                }

    return encontrados


async def crear_psbt(
    rpc,
    txid,
    vout,
    sats,
    witness_script,
    direccion_destino,
    fee_sats
):
    sats = int(sats)
    vout = int(vout)
    fee_sats = int(fee_sats)

    if fee_sats <= 0:
        raise ValueError(
            "La comisión debe ser mayor que 0."
        )

    if fee_sats >= sats:
        raise ValueError(
            "La comisión supera el colateral."
        )

    if not direccion_destino.startswith("tb1"):
        raise ValueError(
            "La dirección de destino no parece Testnet."
        )

    # -------------------------------------------------
    # WITNESS SCRIPT
    # -------------------------------------------------

    if isinstance(witness_script, str):
        script = CScript(
            bytes.fromhex(witness_script)
        )
    else:
        script = CScript(witness_script)

    # -------------------------------------------------
    # DIRECCIÓN P2WSH DEL COLATERAL
    # -------------------------------------------------

    origen = (
        P2WSHBitcoinTestnetAddress
        .from_redeemScript(script)
    )

    script_pubkey = (
        origen.to_scriptPubKey()
    )

    # -------------------------------------------------
    # COMPROBAR UTXO
    # -------------------------------------------------

    raw = await rpc(
        "gettxout",
        [
            txid,
            vout,
            True
        ]
    )
    print("DEBUG GETTXOUT:", raw)

    if raw is None:
        raise ValueError(
            "El UTXO ya no está disponible. "
            "Puede haber sido gastado."
        )

    valor_core = int(
        round(
            float(raw["value"])
            * 100_000_000
        )
    )

    if valor_core != sats:
        raise ValueError(
            f"El valor del UTXO no coincide. "
            f"Esperado: {sats}, "
            f"Core: {valor_core}"
        )

    # -------------------------------------------------
    # VERIFICAR SCRIPT DEL UTXO
    # -------------------------------------------------

    script_core = raw["scriptPubKey"]["hex"]

    if script_core.lower() != script_pubkey.hex().lower():
        raise ValueError(
            "El witness_script no corresponde "
            "al UTXO detectado."
        )
    # -------------------------------------------------
    # CALCULAR SALIDA
    # -------------------------------------------------

    monto_salida = sats - fee_sats
    print("DEBUG MONTO ENTRADA:", sats)
    print("DEBUG FEE:", fee_sats)
    print("DEBUG MONTO SALIDA:", monto_salida)
    if monto_salida <= 330:
     raise ValueError(
        f"La salida sería demasiado pequeña: {monto_salida} sats. "
        f"Aumenta el monto de entrada o reduce la comisión."
    )
    # -------------------------------------------------
    # OBTENER SCRIPT DE LA DIRECCIÓN DESTINO
    # -------------------------------------------------

        # -------------------------------------------------
    # VALIDAR DIRECCIÓN DESTINO
    # -------------------------------------------------

    destino = await rpc(
        "validateaddress",
        [direccion_destino]
    )

    if not destino.get("isvalid"):
        raise ValueError(
            "Bitcoin Core rechazó la dirección destino."
        )

    script_hex = destino.get("scriptPubKey")

    if not script_hex:
        raise ValueError(
            "Bitcoin Core no devolvió scriptPubKey "
            "para la dirección destino."
        )

    destino_script = CScript(
        bytes.fromhex(script_hex)
    )

    # -------------------------------------------------
    # CREAR PSBT
    # -------------------------------------------------

    psbt = PartiallySignedTransaction()

    txin = CTxIn(
        COutPoint(
            lx(txid),
            vout
        )
    )

    psbt_in = PSBT_Input()

    psbt.add_input(
        txin,
        psbt_in
    )

    psbt_out = PSBT_Output()

    psbt.add_output(
        CMutableTxOut(
            monto_salida,
            destino_script
        ),
        psbt_out
    )

    # -------------------------------------------------
    # UTXO SEGWIT
    # -------------------------------------------------

    psbt.inputs[0].set_utxo(
        CMutableTxOut(
            sats,
            script_pubkey
        ),
        psbt.unsigned_tx
    )

   # -------------------------------------------------
    # WITNESS SCRIPT
    # -------------------------------------------------

    if isinstance(witness_script, str):
        script = CScript(
            bytes.fromhex(witness_script)
        )
    else:
        script = CScript(witness_script)

    # -------------------------------------------------
    # DIRECCIÓN P2WSH DEL COLATERAL
    # -------------------------------------------------

    origen = (
        P2WSHBitcoinTestnetAddress
        .from_redeemScript(script)
    )

    script_pubkey = (
        origen.to_scriptPubKey()
    )

    # -------------------------------------------------
    # COMPROBAR UTXO
    # -------------------------------------------------

    raw = await rpc(
        "gettxout",
        [
            txid,
            vout,
            True
        ]
    )
    print("DEBUG GETTXOUT:", raw)

    if raw is None:
        raise ValueError(
            "El UTXO ya no está disponible. "
            "Puede haber sido gastado."
        )

    valor_core = int(
        round(
            float(raw["value"])
            * 100_000_000
        )
    )

    if valor_core != sats:
        raise ValueError(
            f"El valor del UTXO no coincide. "
            f"Esperado: {sats}, "
            f"Core: {valor_core}"
        )

    # -------------------------------------------------
    # VERIFICAR SCRIPT DEL UTXO
    # -------------------------------------------------

    script_core = raw["scriptPubKey"]["hex"]

    if script_core.lower() != script_pubkey.hex().lower():
        raise ValueError(
            "El witness_script no corresponde "
            "al UTXO detectado."
        )
    # -------------------------------------------------
    # CALCULAR SALIDA
    # -------------------------------------------------

    monto_salida = sats - fee_sats

    # -------------------------------------------------
    # OBTENER SCRIPT DE LA DIRECCIÓN DESTINO
    # -------------------------------------------------

        # -------------------------------------------------
    # VALIDAR DIRECCIÓN DESTINO
    # -------------------------------------------------

    destino = await rpc(
        "validateaddress",
        [direccion_destino]
    )

    if not destino.get("isvalid"):
        raise ValueError(
            "Bitcoin Core rechazó la dirección destino."
        )

    script_hex = destino.get("scriptPubKey")

    if not script_hex:
        raise ValueError(
            "Bitcoin Core no devolvió scriptPubKey "
            "para la dirección destino."
        )

    destino_script = CScript(
        bytes.fromhex(script_hex)
    )

    # -------------------------------------------------
    # CREAR PSBT
    # -------------------------------------------------

    psbt = PartiallySignedTransaction()

    txin = CTxIn(
        COutPoint(
            lx(txid),
            vout
        )
    )

    psbt_in = PSBT_Input()

    psbt.add_input(
        txin,
        psbt_in
    )

    psbt_out = PSBT_Output()

    psbt.add_output(
        CMutableTxOut(
            monto_salida,
            destino_script
        ),
        psbt_out
    )

    # -------------------------------------------------
    # UTXO SEGWIT
    # -------------------------------------------------

    psbt.inputs[0].set_utxo(
        CMutableTxOut(
            sats,
            script_pubkey
        ),
        psbt.unsigned_tx
    )

    # -------------------------------------------------
    # WITNESS SCRIPT
    # -------------------------------------------------

    psbt.inputs[0].witness_script = script

    return {
        "psbt": psbt.to_base64(),
        "txid": txid,
        "vout": vout,
        "sats_entrada": sats,
        "fee_sats": fee_sats,
        "sats_salida": monto_salida,
        "direccion_destino": direccion_destino
    }
from bitcointx.core.secp256k1 import get_secp256k1

async def firmar_psbt(
    psbt_base64,
    private_key_hex,
    pubkey_hex
):
    print("FIRMA 1: PSBT cargada")

    try:
        psbt = PartiallySignedTransaction.from_base64(psbt_base64)

    except Exception as e:
        import traceback

        print("ERROR EXACTO AL CARGAR PSBT:")
        traceback.print_exc()

        raise

    print("FIRMA 2: PSBT OK")

    if len(psbt.inputs) != 1:
        raise ValueError(
            "La PSBT debe contener exactamente una entrada."
        )

    inp = psbt.inputs[0]

    print("FIRMA 3: INPUT OK")

    if inp.witness_script is None:
        raise ValueError(
            "La PSBT no contiene witness_script."
        )

    print("FIRMA 4: witness_script OK")

    if inp.witness_utxo is None:
        raise ValueError(
            "La PSBT no contiene witness_utxo."
        )

    print("FIRMA 5: witness_utxo OK")

    private_key = PrivateKey(
        bytes.fromhex(private_key_hex)
    )

    print("FIRMA 6: PrivateKey OK")

    pubkey_bytes = bytes.fromhex(pubkey_hex)

    print("FIRMA 7: CPubKey OK")

    pub_derivado = private_key.public_key.format(
        compressed=True
    )

    if pub_derivado != pubkey_bytes:
        raise ValueError(
            "La clave privada no corresponde "
            "a la clave pública del contrato."
        )

    print("FIRMA 8: CLAVE CORRESPONDE")

    sighash = inp.witness_script.sighash(
        psbt.unsigned_tx,
        0,
        SIGHASH_ALL,
        amount=inp.witness_utxo.nValue,
        sigversion=SIGVERSION_WITNESS_V0
    )

    print("FIRMA 9: SIGHASH OK")

    firma = private_key.sign(
        sighash,
        hasher=None
    )

    print("FIRMA 10: COINCURVE FIRMA OK")

    firma += bytes([int(SIGHASH_ALL)])

    inp.partial_sigs[pubkey_bytes] = firma

    print("FIRMA 11: FIRMA GUARDADA")

    return {
        "psbt": psbt.to_base64(),
        "firmas_nuevas": 1,
        "firmas_faltantes": None,
        "final": False
    }
async def finalizar_y_transmitir(rpc, psbt_base64):

    print("FINALIZAR 1: Cargando PSBT")

    psbt = PartiallySignedTransaction.from_base64(psbt_base64)

    if len(psbt.inputs) != 1:
        raise ValueError(
            "La PSBT debe tener exactamente una entrada."
        )

    inp = psbt.inputs[0]

    if inp.witness_script is None:
        raise ValueError(
            "Falta witness_script."
        )

    if inp.witness_utxo is None:
        raise ValueError(
            "Falta witness_utxo."
        )

    print("FINALIZAR 2: Datos de entrada OK")

    witness_script_bytes = bytes(inp.witness_script)

    print(
        "WITNESS SCRIPT:",
        witness_script_bytes.hex()
    )

    # ---------------------------------------------------------
    # OBTENER LAS PUBKEYS DEL WITNESS SCRIPT
    # ---------------------------------------------------------

    script = inp.witness_script

    elementos = list(script)

    pubkeys_script = []

    for elemento in elementos:

        if isinstance(elemento, bytes):

            if len(elemento) == 33:

                pubkeys_script.append(
                    bytes(elemento)
                )

    if len(pubkeys_script) < 3:
        raise ValueError(
            "No se encontraron las 3 pubkeys del witness_script."
        )

    # Las primeras 3 pubkeys corresponden al 2-de-3
    pubkeys_script = pubkeys_script[:3]

    print("PUBKEYS DEL WITNESS SCRIPT:")

    for i, pubkey in enumerate(pubkeys_script, 1):
        print(
            f"PUBKEY SCRIPT {i}:",
            pubkey.hex()
        )

    # ---------------------------------------------------------
    # OBTENER FIRMAS DE LA PSBT
    # ---------------------------------------------------------

    partial_sigs = inp.partial_sigs

    if len(partial_sigs) < 2:
        raise ValueError(
            f"Se necesitan al menos 2 firmas. "
            f"Actualmente hay {len(partial_sigs)}."
        )

    print("PUBKEYS CON FIRMA EN LA PSBT:")

    for pubkey in partial_sigs.keys():
        print(
            bytes(pubkey).hex()
        )

    # ---------------------------------------------------------
    # BUSCAR LAS 2 FIRMAS QUE CORRESPONDEN AL SCRIPT
    # ---------------------------------------------------------

    firmas_ordenadas = []

    for pubkey_script in pubkeys_script:

        firma = None

        for pubkey_psbt, firma_psbt in partial_sigs.items():

            if bytes(pubkey_psbt) == pubkey_script:

                firma = firma_psbt
                break

        if firma is not None:

            firmas_ordenadas.append(
                (
                    pubkey_script,
                    firma
                )
            )

    if len(firmas_ordenadas) < 2:

        encontrados = [
            pubkey.hex()
            for pubkey, firma in firmas_ordenadas
        ]

        raise ValueError(
            "No se encontraron 2 firmas compatibles "
            "con las pubkeys del witness_script.\n"
            f"Encontradas: {encontrados}"
        )

    print(
        "FINALIZAR 3:",
        len(firmas_ordenadas),
        "firmas compatibles encontradas"
    )

    # ---------------------------------------------------------
    # MOSTRAR LAS FIRMAS EN ORDEN DEL SCRIPT
    # ---------------------------------------------------------

    for i, (pubkey, firma) in enumerate(
        firmas_ordenadas,
        1
    ):

        print(
            f"FIRMA {i} PUBKEY:",
            pubkey.hex()
        )

        print(
            f"FIRMA {i}:",
            firma.hex()
        )

    # ---------------------------------------------------------
    # USAR SOLAMENTE 2 FIRMAS
    # ---------------------------------------------------------

    if len(firmas_ordenadas) > 2:

        firmas_ordenadas = firmas_ordenadas[:2]

    firma_script1 = firmas_ordenadas[0][1]
    firma_script2 = firmas_ordenadas[1][1]

    print(
        "FIRMA SCRIPT 1:",
        firma_script1.hex()
    )

    print(
        "FIRMA SCRIPT 2:",
        firma_script2.hex()
    )

    # ---------------------------------------------------------
    # LIMPIAR CAMPOS NO FINALES
    # ---------------------------------------------------------

    inp._clear_nonfinal_fields()

    # ---------------------------------------------------------
    # CONSTRUIR WITNESS FINAL
    # ---------------------------------------------------------
    #
    # Para:
    #
    # OP_IF
    # OP_2
    # pubkey1
    # pubkey2
    # pubkey3
    # OP_3
    # OP_CHECKMULTISIG
    #
    # El witness es:
    #
    # ""
    # firma1
    # firma2
    # 01
    # witness_script
    #
    # El "" es necesario por CHECKMULTISIG.
    #

    from bitcointx.core.script import CScriptWitness

    inp.final_script_witness = CScriptWitness([
        b"",
        firma_script1,
        firma_script2,
        b"\x01",
        witness_script_bytes
    ])

    print(
        "FINALIZAR 4: Witness final construido"
    )

    print(
        "FINAL WITNESS:",
        [
            x.hex()
            for x in inp.final_script_witness
        ]
    )

    # ---------------------------------------------------------
    # SERIALIZAR PSBT
    # ---------------------------------------------------------

    psbt_final = psbt.to_base64()

    print(
        "PSBT ANTES DE FINALIZE:"
    )

    print(psbt_final)

    # ---------------------------------------------------------
    # DEBUG decodepsbt
    # ---------------------------------------------------------

    debug_psbt = await rpc(
        "decodepsbt",
        [psbt_final]
    )

    print(
        "DECODEPSBT:"
    )

    print(debug_psbt)

    # ---------------------------------------------------------
    # FINALIZAR CON BITCOIN CORE
    # ---------------------------------------------------------

    print(
        "FINALIZAR 5: Probando finalizepsbt"
    )

    resultado = await rpc(
        "finalizepsbt",
        [
            psbt_final,
            True
        ]
    )

    print(
        "DEBUG FINALIZEPSBT:",
        resultado
    )

    if resultado.get("complete") is not True:

        raise ValueError(
            "Bitcoin Core todavía no pudo finalizar:\n"
            f"{resultado}"
        )

    hex_final = resultado.get("hex")

    if not hex_final:

        raise ValueError(
            "Bitcoin Core no devolvió "
            "la transacción final."
        )

    print(
        "FINALIZAR 6: Transacción final creada"
    )

    # ---------------------------------------------------------
    # DECODIFICAR TRANSACCIÓN FINAL
    # ---------------------------------------------------------

    decoded = await rpc(
        "decoderawtransaction",
        [hex_final]
    )

    print(
        "DEBUG TRANSACTION FINAL:",
        decoded
    )

    # ---------------------------------------------------------
    # TRANSMITIR
    # ---------------------------------------------------------

    print(
        "FINALIZAR 7: Transmitiendo a Testnet"
    )

    txid = await rpc(
        "sendrawtransaction",
        [hex_final]
    )

    print(
        "FINALIZAR 8: TXID:",
        txid
    )

    return {
        "txid": txid,
        "hex": hex_final
    }
