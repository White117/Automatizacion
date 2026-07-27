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

#  CONFIGURACIÓN DE CORREO ELECTRÓNICO 
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587
CORREO_EMISOR = os.getenv("CORREO_EMISOR")
CONTRASENA_APP = os.getenv("CONTRASENA_APP")
CORREO_DESTINATARIO = os.getenv("CORREO_DESTINATARIO")


def inicializar_db():
    """Crea la tabla de mensajes con la columna 'procesado' si aún no existe."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS mensajes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT,
            telefono TEXT,
            contenido TEXT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            procesado INTEGER DEFAULT 0
        )
    """)
    conn.commit()
    conn.close()


def limpiar_bd():
    """Vacía todos los registros de la base de datos."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM mensajes")
    conn.commit()
    conn.close()
    print("\n[BD] Base de datos limpiada con éxito.")


def ver_mensajes_actuales():
    """Muestra por consola todos los mensajes y su estado de procesamiento."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT id, nombre, telefono, contenido, timestamp, procesado FROM mensajes")
    filas = cursor.fetchall()
    conn.close()

    if not filas:
        print("\nNo hay mensajes guardados en la base de datos todavía.")
        return

    print(f"\n--- MENSAJES EN LA BD ({len(filas)}) ---")
    for f in filas:
        id_msg = f[0]
        nombre = f[1]
        telefono = f[2]
        contenido = f[3]
        timestamp = f[4]
        procesado = "Sí" if f[5] == 1 else "No (Pendiente)"
        
        print(f"[{id_msg}] De: {nombre} ({telefono}) | Fecha: {timestamp} | Procesado: {procesado}")
        print(f"    Contenido: {contenido}")
        print("-" * 40)


def enviar_correo_reporte(cuerpo_reporte):
    """Envía el reporte generado por la IA a través del servidor SMTP de Gmail."""
    print("\nPreparando y enviando el correo electrónico...")
    try:
        mensaje = MIMEMultipart()
        mensaje["From"] = CORREO_EMISOR
        mensaje["To"] = CORREO_DESTINATARIO
        mensaje["Subject"] = "Reporte Ejecutivo de Nuevos Mensajes - WhatsApp Bot"

        mensaje.attach(MIMEText(cuerpo_reporte, "plain", "utf-8"))

        servidor = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
        servidor.starttls()
        servidor.login(CORREO_EMISOR, CONTRASENA_APP)
        servidor.sendmail(CORREO_EMISOR, CORREO_DESTINATARIO, mensaje.as_string())
        servidor.quit()

        print("¡Correo enviado exitosamente a tu bandeja de entrada!")
        return True
    except Exception as e:
        print(f"Error al enviar el correo: {e}")
        return False


def procesar_resumen_con_ollama():
    """Consulta únicamente los mensajes pendientes (procesado = 0), los procesa 
       con Ollama, envía el correo y marca esos mensajes como procesados (1).
    """
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    # Filtramos estrictamente los mensajes que aún no han sido enviados en ningún reporte
    cursor.execute("SELECT id, nombre, telefono, contenido, timestamp FROM mensajes WHERE procesado = 0")
    filas = cursor.fetchall()

    if not filas:
        print("\nNo hay mensajes nuevos pendientes para procesar.")
        conn.close()
        return

    # Prepara la lista estructurada con los IDs para actualizar su estado después
    mensajes_lista = []
    ids_a_marcar = []
    
    for f in filas:
        id_msg = f[0]
        nombre = f[1]
        telefono = f[2]
        contenido = f[3]
        timestamp = f[4]
        
        ids_a_marcar.append(id_msg)
        mensajes_lista.append({
            "remitente": f"{nombre} ({telefono})",
            "contenido": contenido,
            "timestamp": timestamp
        })

    conn.close()

    print(f"\nAnalizando {len(mensajes_lista)} mensajes nuevos con Llama 3.1... por favor espera...")

    prompt_sistema = """
Eres un asistente ejecutivo de inteligencia artificial para una empresa. 
Recibirás un listado en formato JSON de mensajes de WhatsApp nuevos recibidos recientemente.

REGLAS DE CLASIFICACION ESTRICTAS:
1. 🔴 URGENTE / CRITICO: Caídas de sistemas, errores graves, servidores caídos, emergencias o bloqueos.
2. 🟡 OPORTUNIDADES COMERCIALES / VENTAS: Interés en precios, cotizaciones, compras o adquisición de productos.
3. 🟢 INFORMATIVO / OPERATIVO: Consultas reales de clientes, preguntas sobre procesos, horarios o avisos internos válidos.
4. ⚪ SPAM / OTROS: Mensajes vacíos, pruebas de teclado aleatorias (como "asd", "123", letras al azar), cadenas, memes, bromas o publicidad.

FORMATO DE SALIDA OBLIGATORIO:
Devuelve el reporte manteniendo estrictamente los emojis y encabezados. 
Para cada mensaje encontrado, NO muestres código JSON ni estructuras técnicas. Escríbelo de forma limpia y legible usando este formato exacto por cada línea:
- "Contenido del mensaje" (Remitente: [número], Hora: [timestamp])

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
        "prompt": f"{prompt_sistema}\n\nMENSAJES NUEVOS A ANALIZAR:\n{prompt_usuario}",
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


            correo_enviado = enviar_correo_reporte(resultado)
            
            if correo_enviado:
                conn = sqlite3.connect(DB_NAME)
                cursor = conn.cursor()
                for id_msg in ids_a_marcar:
                    cursor.execute("UPDATE mensajes SET procesado = 1 WHERE id = ?", (id_msg,))
                conn.commit()
                conn.close()
            
        else:
            print(f"Error en la respuesta de Ollama: {response.status_code}")
    except requests.exceptions.ConnectionError:
        print("Error: Asegúrate de que Ollama esté abierto y ejecutándose.")


if __name__ == "__main__":
    inicializar_db()


    # MODO MANUAL 

    
    while True:
        print("\n--- MENÚ DE DEMOSTRACIÓN WHATSAPP BOT (MANUAL) ---")
        print("1. Ver mensajes en la BD (y su estado de procesamiento)")
        print("2. Procesar únicamente los mensajes NUEVOS (Ollama + Correo)")
        print("3. Limpiar base de datos")
        print("4. Salir")
        
        opcion = input("Elige una opción (1-4): ").strip()
        
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
    

  
     # MODO AUTOMÁTICO
    
    #schedule.every(2).minutes.do(procesar_resumen_con_ollama)
    #while True:
    #     schedule.run_pending()
    #     time.sleep(1)