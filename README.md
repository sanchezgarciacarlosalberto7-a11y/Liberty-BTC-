🔐 Liberty-BTC

Bot de préstamos con Bitcoin desarrollado en Python e integrado con Telegram y Bitcoin Core.

1. 📥 Cómo instalar

Requisitos: Python, Git, Bitcoin Core y un bot de Telegram.

Clona el repositorio:

git clone https://github.com/sanchezgarciacarlosalberto7-a11y/Liberty-BTC-.git
cd Liberty-BTC-

Crea y activa el entorno virtual:

python3 -m venv .venv
source .venv/bin/activate

Instala las dependencias:

pip install -r requirements.txt

2. 🤖 Configurar el token de Telegram

1. Abre Telegram y busca "@BotFather".
2. Ejecuta "/newbot" y sigue las instrucciones.
3. Copia el token que te proporciona.
4. Guárdalo como variable de entorno, sin publicarlo en GitHub.

export TOKEN="TU_TOKEN_DE_TELEGRAM"

El nombre "TOKEN" debe coincidir con el que utiliza el código. Si el proyecto emplea otro nombre o un archivo ".env", configura el token según su implementación.

3. ₿ Configurar Bitcoin Core

Instala Bitcoin Core y configura la conexión RPC que utiliza Liberty-BTC.

Comprueba que Bitcoin Core está ejecutándose en la red correcta y que el bot puede conectarse a él.

Importante: protege las credenciales RPC y utiliza una red de pruebas durante el desarrollo.

4. ▶️ Iniciar el bot

Activa el entorno virtual e inicia el programa principal:

python bot_prestamos.py

Si aparece un error, revisa las dependencias, el token, la conexión RPC y los registros del programa.

5. ⚙️ Cómo funciona Liberty-BTC

1. Un usuario publica una oferta de préstamo.
2. Otro usuario acepta las condiciones.
3. El bot registra la operación y espera el depósito de Bitcoin.
4. Bitcoin Core permite comprobar el depósito y sus confirmaciones.
5. El código controla los estados del préstamo, el LTV y los vencimientos.
6. Los participantes preparan y firman las transacciones correspondientes.
7. Se verifica el resultado antes de cerrar la operación.

6. 🧠 Cómo funciona el código

- Telegram: recibe comandos y comunica a los participantes.
- Python: ejecuta las reglas del préstamo y controla sus estados.
- Bitcoin Core: consulta la cadena de bloques y permite interactuar con las transacciones.
- SQLite: guarda los datos de las operaciones, según la implementación.
- PSBT y firmas: permiten preparar y coordinar transacciones que deben autorizar sus firmantes.
- Pruebas: ayudan a detectar errores y verificar las reglas del sistema.

El servidor debe coordinar las operaciones, no firmar por todos los participantes. Cada usuario debe conservar el control de su clave privada.

7. 📊 Diagramas

Arquitectura

flowchart TD
    A[Usuarios] <--> B[Telegram]
    B <--> C[Código Python]
    C <--> D[(SQLite)]
    C <--> E[Bitcoin Core]
    A --> F[Firmas de los participantes]
    F --> E
    E <--> G[Red Bitcoin]

Flujo del préstamo

flowchart TD
    A[Publicar oferta] --> B[Aceptar préstamo]
    B --> C[Depositar garantía]
    C --> D[Verificar depósito]
    D --> E[Supervisar operación]
    E --> F[Preparar transacción]
    F --> G[Firmar y verificar]
    G --> H[Transmitir transacción]
    H --> I[Verificar resultado]

Firmas multisig 2 de 3

flowchart TD
    A[Participante A] --> D[Multisig 2 de 3]
    B[Participante B] --> D
    C[Tercer firmante] --> D
    D --> E{¿Dos firmas válidas?}
    E -- No --> F[No se autoriza el gasto]
    E -- Sí --> G[Bitcoin verifica las condiciones]

Estado del proyecto: en desarrollo. Los diagramas representan el funcionamiento previsto y deben contrastarse con el código real. No utilices fondos reales hasta verificar las firmas, la seguridad y la recuperación de los BTC.
