# HLK-LD2450 mmWave Radar Spatial Tracking & Presence Detection System

[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/downloads/)
[![PlatformIO](https://img.shields.io/badge/PlatformIO-ESP32-orange.svg)](https://platformio.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

Sistema integrado de detecção de presença humana, rastreamento espacial multiponto (até 3 alvos simultâneos) e geofencing cartesiano 2D utilizando o sensor radar FMCW **Hi-Link HLK-LD2450 (24 GHz)**, microcontrolador **ESP32**, e pipeline de processamento em **Python 3.10+** com interface de terminal (Rich) e plotagem gráfica em tempo real (Matplotlib).

---

## 📐 Visão Geral da Arquitetura

```
+-------------------------------------------------------------+
|                     HARDWARE LAYER                          |
|                                                             |
|   +-------------------+              +------------------+   |
|   |   HLK-LD2450      |    UART2     |   ESP32 DevKit   |   |
|   |  24GHz mmWave     | ------------>|   (esp32dev)     |   |
|   |  Radar (256kbps)  |  GPIO 16/17  |  Frame Validator |   |
|   +-------------------+              +--------+---------+   |
+-----------------------------------------------|-------------+
                                                |
                       USB Serial / WiFi UDP    | (30-byte frames)
                                                v
+-------------------------------------------------------------+
|                      HOST LAYER (PC)                        |
|                                                             |
|  +-------------------------------------------------------+  |
|  | Transport Layer (SerialTransport / UDPTransport)      |  |
|  +---------------------------+---------------------------+  |
|                              | byte stream                  |
|                              v                              |
|  +-------------------------------------------------------+  |
|  | LD2450Parser (Sync 0xAA..0x00, Sign-Magnitude Decode)  |  |
|  +---------------------------+---------------------------+  |
|                              | RadarFrame (3 targets)       |
|                              v                              |
|  +-------------------------------------------------------+  |
|  | ZoneManager (AABB Geofencing & Occupancy Evaluation)  |  |
|  +---------------------------+---------------------------+  |
|                              |                              |
|              +---------------+---------------+              |
|              v                               v              |
|     +------------------+            +------------------+    |
|     |  CLIView (Rich)  |            | PlotView (MPL)   |    |
|     |  Live Dashboard  |            | 2D Radar Canvas  |    |
|     +------------------+            +------------------+    |
+-------------------------------------------------------------+
```

---

## 🔌 Esquema Elétrico e Conexões

O sensor HLK-LD2450 opera em 5V e possui consumo instantâneo de até 200mA durante a emissão de pulsos de radiofrequência. Conecte-o diretamente aos pinos de 5V e GND da ESP32 ou a uma fonte regulada externa.

| Pino HLK-LD2450 | Pino ESP32 DevKit | Função | Observações |
| :--- | :--- | :--- | :--- |
| **VCC (5V)** | **VIN / 5V** | Alimentação | Alimentação estável de 5V |
| **GND** | **GND** | Terra Comum | Referência comum |
| **TX** | **GPIO 16 (RX2)** | Dados do Radar | Entrada UART2 na ESP32 |
| **RX** | **GPIO 17 (TX2)** | Comandos ao Radar | Saída UART2 da ESP32 |

> **Nota:** A taxa de comunicação nativa da UART do HLK-LD2450 é de **256000 bps**, 8 bits de dados, 1 stop bit, sem paridade.

---

## 📡 Protocolo do Sensor HLK-LD2450

O sensor envia continuamente frames de **30 bytes** contendo a informação de até 3 alvos rastreados:

```
[4 bytes Header] + [3 alvos x 8 bytes = 24 bytes] + [2 bytes Tail] = 30 bytes
```

### Estrutura Detalhada do Frame

| Campo | Tamanho | Valor / Formato | Descrição |
| :--- | :--- | :--- | :--- |
| **Header** | 4 bytes | `0xAA 0xFF 0x03 0x00` | Delimitador de início de frame de relatório |
| **Alvo 1** | 8 bytes | `[X, Y, Velocidade, Resolução]` | Coordenadas, velocidade e resolução do alvo 1 |
| **Alvo 2** | 8 bytes | `[X, Y, Velocidade, Resolução]` | Coordenadas, velocidade e resolução do alvo 2 |
| **Alvo 3** | 8 bytes | `[X, Y, Velocidade, Resolução]` | Coordenadas, velocidade e resolução do alvo 3 |
| **Tail** | 2 bytes | `0x55 0xCC` | Delimitador de final de frame |

### Codificação de Coordenadas (Sign-Magnitude 16-bit Little Endian)
Cada coordenada $X$, $Y$ e a $Velocidade$ utilizam 2 bytes onde:
- **Bit 15 (MSB)**: Bit de sinal (`0` = Positivo, `1` = Negativo).
- **Bits 0–14**: Magnitude absoluta do valor.
  - $X$: Posição lateral em milímetros ($-6000$ a $+6000$ mm). Valores negativos indicam o lado esquerdo; positivos, o lado direito.
  - $Y$: Distância frontal em milímetros ($0$ a $+6000$ mm).
  - $Velocidade$: Velocidade radial em cm/s. Valores negativos indicam aproximação do sensor; positivos indicam afastamento.
  - $Resolução$: Resolução/precisão da distância em milímetros (uint16).

---

## 📁 Estrutura do Repositório

```text
.
├── .gitignore               # Ignora arquivos temporários, builds PlatformIO, .venv, etc.
├── README.md                # Documentação técnica completa
├── requirements.txt         # Dependências do backend Python (pyserial, rich, matplotlib)
├── config/
│   └── settings.json        # Configuração de portas, baudrates, rede e zonas AABB
├── esp32/
│   ├── platformio.ini       # Configuração de build e upload da ESP32 (PlatformIO)
│   ├── include/
│   │   └── config.h         # Mapeamento de pinos, baudrates e credenciais Wi-Fi/UDP
│   └── src/
│       └── main.cpp         # Firmware da ESP32 (leitura UART2, framing e encaminhamento)
├── core/
│   ├── __init__.py          # Exportação dos componentes principais
│   ├── ld2450_parser.py     # Parser binário de frames com validação de cabeçalho e sinal
│   ├── transport.py         # Camada de transporte abstrata (Serial, UDP e Mock)
│   └── zone_manager.py      # Gerenciador de zonas espaciais (AABB) e detecção de ocupação
├── views/
│   ├── __init__.py          # Exportação das views
│   ├── cli_view.py          # Dashboard em terminal usando Rich
│   └── plot_view.py         # Visualização cartesiana 2D em tempo real com Matplotlib
└── main.py                  # Ponto de entrada do sistema
```

---

## 🚀 Instalação e Execução

### 1. Gravação do Firmware na ESP32 (PlatformIO)

Requisitos: [PlatformIO Core (CLI)](https://docs.platformio.org/en/latest/core/installation/methods/installer-script.html) ou a extensão do PlatformIO no VSCode.

```bash
# Entre na pasta do firmware
cd esp32

# Compile o firmware
pio run

# Grave na ESP32 conectada via USB
pio run --target upload

# Opcional: Abra o monitor serial da ESP32
pio device monitor
```

> **Dica Wi-Fi / UDP:** Para transmitir os dados sem fio via UDP ao invés da porta USB serial, configure `#define ENABLE_WIFI_UDP true` em [esp32/include/config.h](file:///Users/igoraraujo/PycharmProjects/HeartBeat-Sensor/esp32/include/config.h) e informe seu SSID, senha do Wi-Fi e o IP do PC.

---

### 2. Configuração do Backend Python

Requisitos: **Python 3.10+** instalado.

```bash
# Retorne à raiz do projeto
cd ..

# Crie e ative o ambiente virtual
python3 -m venv .venv
source .venv/bin/activate    # No Linux/macOS
# .venv\Scripts\activate     # No Windows

# Instale as dependências
pip install -r requirements.txt
```

---

### 3. Configuração das Zonas e Portas

Edite o arquivo [config/settings.json](file:///Users/igoraraujo/PycharmProjects/HeartBeat-Sensor/config/settings.json) para definir a porta serial do seu dispositivo e as coordenadas das zonas de interesse (AABB - Axis-Aligned Bounding Boxes em milímetros):

```json
{
  "transport": {
    "type": "serial",
    "serial": {
      "port": "/dev/ttyUSB0",
      "baudrate": 115200,
      "timeout": 1.0
    }
  },
  "zones": [
    {
      "name": "Mesa de Trabalho",
      "x_min": -1000,
      "x_max": 800,
      "y_min": 600,
      "y_max": 2200,
      "color": "#3498db"
    }
  ]
}
```

---

### 4. Executando o Sistema

#### Modo 1: Dashboard CLI no Terminal (Rich)
Ideal para monitoramento rápido, headless ou servidores remotos:
```bash
python main.py --view cli --port /dev/ttyUSB0
```

#### Modo 2: Plot Cartesiano 2D Gráfico (Matplotlib)
Abre o radar com cone de visibilidade (FOV 120°), zonas retangulares coloridas e vetores de velocidade dos alvos:
```bash
python main.py --view plot --port /dev/ttyUSB0
```

#### Modo 3: Ambos os Modos Simultâneos
```bash
python main.py --view both --port /dev/ttyUSB0
```

#### Modo 4: Teste Offline / Simulação (Sem Hardware Conectado)
O projeto inclui um gerador de telemetria sintética (`MockTransport`) que emula alvos se movimentando entre as zonas configuradas para validação do pipeline:
```bash
python main.py --transport mock --view both
```

#### Modo 5: Recepção via Wi-Fi UDP
```bash
python main.py --transport udp --view both
```

---

## 🧪 Parâmetros de Linha de Comando (`main.py`)

| Argumento | Opções | Padrão | Descrição |
| :--- | :--- | :--- | :--- |
| `-c`, `--config` | Caminho do arquivo | `config/settings.json` | Arquivo JSON de configurações |
| `-v`, `--view` | `cli`, `plot`, `both` | `cli` | Modo de visualização ativo |
| `-t`, `--transport` | `serial`, `udp`, `mock` | Configuração JSON | Tipo de transporte utilizado |
| `-p`, `--port` | String (`COM3`, `/dev/...`) | Configuração JSON | Sobrescreve a porta serial |
| `-b`, `--baud` | Inteiro (`115200`, `256000`)| Configuração JSON | Sobrescreve o baudrate da porta |

---

## 🛠️ Licença

Este projeto está sob a licença [MIT](LICENSE).