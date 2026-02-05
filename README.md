# 🤖 PriBot

PriBot es un bot de WhatsApp desarrollado en Python que puede:

- ⏰ Crear recordatorios por usuario
- 🧠 Recordar información (memoria global)
- 💬 Entender lenguaje natural
- 🧩 Integrar IA local (GPT-4-All) de forma opcional
- 🔒 Funcionar sin depender de servicios pagos

El proyecto está diseñado con una arquitectura modular y extensible,
pensada para producción real.

---

## ✨ Features

- WhatsApp Cloud API (Meta)
- Webhooks con Flask
- Recordatorios con APScheduler
- Persistencia en SQLite
- Parser híbrido:
  - Reglas + regex
  - Fallback manual de tiempo
  - IA local opcional (GPT-4-All)
- Sin costos obligatorios de API

---

## 🧱 Arquitectura

```text
WhatsApp
   ↓
Meta Webhook
   ↓
Flask API
   ↓
┌─────────────────────┐
│ Intent Router       │
│  - Reglas           │
│  - IA (opcional)    │
└─────────────────────┘
   ↓
┌───────────┬───────────┐
│ Reminders │ Memory    │
│ Scheduler │ SQLite DB │
└───────────┴───────────┘
```

## 📁 Estructura del proyecto

```text
PriBot/
│
├── app.py                  # Flask app + webhook
├── db.py                   # SQLite + helpers
├── scheduler.py            # APScheduler setup
├── reminders_controller.py # Recordatorios por usuario
├── memory_controller.py    # Memoria global
├── ai_controller.py        # IA local (GPT-4-All)
│
├── .env.example            # Variables de entorno (ejemplo)
├── .gitignore
├── README.md
└── requirements.txt
```

## ⚙️ Requisitos

- Python 3.10+
- Cuenta de WhatsApp Cloud API (Meta)
- pip / venv
- Opcional:
GPT-4-All (IA local)

## 🚀 Instalación

```bash
git clone <repo-url>
cd PriBot
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## 🔐 Variables de entorno
Crear un archivo .env (NO se sube al repo):

```text
VERIFY_TOKEN=pribot_verify_123
WHATSAPP_TOKEN=xxxxxxxx
PHONE_NUMBER_ID=xxxxxxxx
```

## Ejecutar en local

```bash
python app.py
```

## 💬 Comandos soportados

Recordatorios
```text
recordar tomar agua en 30 segundos
mis recordatorios
```

Memoria
```text
recuerda perro = Luna
dato perro
```

Lenguaje natural con IA
```text
Acuérdame tomar agua en 30 segundos
Guardá que mi perro se llama Luna
Cómo se llama mi perro?
```

## 📌 Estado del proyecto

✅ MVP funcional

🚧 Mejoras futuras:
- Borrar recordatorios
- Recordatorios recurrentes
- Permisos de memoria
- Re-agendar al reiniciar
- IA más contextual

## 🧑‍💻 Autora
Fabiola Jiménez

Software Engineer · Backend · Automation · Security

## 🖤 Licencia
MIT