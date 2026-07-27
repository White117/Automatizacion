import os
import sqlite3
import json
import requests
import smtplib
import time
import schedule
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from dotenv import load_dotenv

# Carga las variables secretas desde el archivo .env
load_dotenv()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_NAME = os.path.join(BASE_DIR, "mensajes_demo.db")

# --- CONFIGURACION DE CORREO (Seguras por variables de entorno) ---
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587
CORREO_EMISOR = os.getenv("CORREO_EMISOR")
CONTRASENA_APP = os.getenv("CONTRASENA_APP")
CORREO_DESTINATARIO = os.getenv("CORREO_DESTINATARIO")


# --------------------------------

def inicializar_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS mensajes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT,
            telefono TEXT,
            contenido TEXT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()

def limpiar_bd():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM mensajes")
    conn.commit()
    conn.close()
    print("Base de datos limpiada con exito.")

def ver_mensajes_actuales():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT id, nombre, telefono, contenido, timestamp FROM mensajes")
    filas = cursor.fetchall()
    conn.close()

    if not filas:
        print("\nNo hay mensajes guardados en la base de datos todavia.")
        return

    print(f"\n--- MENSAJES REALES EN LA BD ({len(filas)}) ---")
    for f in filas:
        id_msg = f[0]
        nombre = f[1]
        telefono = f[2]
        contenido = f[3]
        timestamp = f[4]
        
        print(f"[{id_msg}] De: {nombre} ({telefono}) | Fecha: {timestamp}")
        print(f"    Contenido: {contenido}")
        print("-" * 40)

def enviar_correo_reporte(cuerpo_reporte):
    print("\nPreparando y enviando el correo electronico...")
    try:
        mensaje = MIMEMultipart()
        mensaje["From"] = CORREO_EMISOR
        mensaje["To"] = CORREO_DESTINATARIO
        mensaje["Subject"] = "Reporte Ejecutivo Diario - WhatsApp Bot"

        mensaje.attach(MIMEText(cuerpo_reporte, "plain", "utf-8"))

        servidor = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
        servidor.starttls()
        servidor.login(CORREO_EMISOR, CONTRASENA_APP)
        servidor.sendmail(CORREO_EMISOR, CORREO_DESTINATARIO, mensaje.as_string())
        servidor.quit()

        print("¡Correo enviado exitosamente a tu bandeja de entrada!")
    except Exception as e:
        print(f"Error al enviar el correo: {e}")

def procesar_resumen_con_ollama():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT id, nombre, telefono, contenido, timestamp FROM mensajes")
    filas = cursor.fetchall()
    conn.close()

    if not filas:
        print("No hay mensajes nuevos en la base de datos para analizar.")
        return

    # Mapeo corregido: id, nombre, telefono, contenido, timestamp
    mensajes_lista = []
    for f in filas:
        nombre = f[1]
        telefono = f[2]
        contenido = f[3]
        timestamp = f[4]
        
        mensajes_lista.append({
            "remitente": f"{nombre} ({telefono})",
            "contenido": contenido,
            "timestamp": timestamp
        })

    print(f"\nAnalizando {len(mensajes_lista)} mensajes reales con Llama 3.1... por favor espera un momento...")

    prompt_sistema = """
Eres un asistente ejecutivo de inteligencia artificial para una empresa. 
Recibiras un listado en formato JSON de mensajes de WhatsApp recibidos durante el dia.

REGLAS DE CLASIFICACION ESTRICTAS:
1. 🔴 URGENTE / CRITICO: Caidas de sistemas, errores graves, servidores caidos, emergencias o bloqueos.
2. 🟡 OPORTUNIDADES COMERCIALES / VENTAS: Interes en precios, cotizaciones, compras o adquisicion de productos.
3. 🟢 INFORMATIVO / OPERATIVO: Consultas reales de clientes, preguntas sobre procesos, horarios o avisos internos validos.
4. ⚪ SPAM / OTROS: Mensajes vacíos, pruebas de teclado aleatorias (como "asd", "123", letras al azar), cadenas, memes, bromas o publicidad.

FORMATO DE SALIDA OBLIGATORIO:
Devuelve el reporte manteniendo estrictamente los emojis y encabezados. 
Para cada mensaje encontrado, NO muestres código JSON ni estructuras técnicas. Escríbelo de forma limpia y legible usando este formato exacto por cada línea:
- "Contenido del mensaje" (Remitente: [número], Hora: [timestamp])

Si una categoría no tiene mensajes, escribe exactamente:
- No se encontraron mensajes en esta categoría.

Sigue estrictamente este esquema:

**Informe de Clasificación de Mensajes de WhatsApp**

**🔴 URGENTE / CRITICO**
- [Mensajes o "No se encontraron mensajes en esta categoría."]

**🟡 OPORTUNIDADES COMERCIALES / VENTAS**
- [Mensajes o "No se encontraron mensajes en esta categoría."]

**🟢 INFORMATIVO / OPERATIVO**
- [Mensajes o "No se encontraron mensajes en esta categoría."]

**⚪ SPAM / OTROS**
- [Mensajes o "No se encontraron mensajes en esta categoría."]
"""

    prompt_usuario = json.dumps(mensajes_lista, indent=2, ensure_ascii=False)
    payload = {
        "model": "llama3.1",
        "prompt": f"{prompt_sistema}\n\nMENSAJES A ANALIZAR:\n{prompt_usuario}",
        "stream": False
    }

    try:
        response = requests.post("http://localhost:11434/api/generate", json=payload)
        if response.status_code == 200:
            resultado = response.json().get("response", "")
            
            print("\n" + "="*50)
            print("REPORTE GENERADO:")
            print("="*50)
            print(resultado)
            print("="*50 + "\n")

            enviar_correo_reporte(resultado)
            
        else:
            print(f"Error en la respuesta de Ollama: {response.status_code}")
    except requests.exceptions.ConnectionError:
        print("Error: Asegurate de que Ollama este abierto y ejecutandose.")

# MENU INTERACTIVO DEMO 
if __name__ == "__main__":
    inicializar_db()
    
    while True:
        print("\n--- MENU DE DEMOSTRACION WHATSAPP BOT ---")
        print("1. Ver mensajes reales guardados en node")
        print("2. Enviar por correo")
        print("3. Limpiar db")
        print("4. Salir")
        
        opcion = input("Elige una opcion (1-4): ").strip()
        
        if opcion == "1":
            ver_mensajes_actuales()
        elif opcion == "2":
            procesar_resumen_con_ollama()
        elif opcion == "3":
            limpiar_bd()
        elif opcion == "4":
            print("¡Saliendo de la demo!")
            break
        else:
            print("Opción no válida. Elige un número del 1 al 4.")