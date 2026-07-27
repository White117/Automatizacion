console.log('Iniciando script de WhatsApp...');

const { makeWASocket, useMultiFileAuthState, DisconnectReason } = require('@whiskeysockets/baileys');
const qrcode = require('qrcode-terminal');
const pino = require('pino');
const sqlite3 = require('sqlite3').verbose();

// Conexión a la base de datos
const DB_NAME = 'mensajes_demo.db';

// Control de spam simple en memoria
const controlSpam = {};

function esSpam(numeroRemitente, contenido) {
    if (contenido.length > 500) return true;
    
    const ahora = Date.now();
    const ventanaTiempoMs = 10000; // 10 segundos
    const maxMensajesPermitidos = 5;

    if (!controlSpam[numeroRemitente]) {
        controlSpam[numeroRemitente] = { count: 1, timestamp: ahora };
        return false;
    }

    if (ahora - controlSpam[numeroRemitente].timestamp > ventanaTiempoMs) {
        controlSpam[numeroRemitente] = { count: 1, timestamp: ahora };
        return false;
    }

    controlSpam[numeroRemitente].count++;
    return controlSpam[numeroRemitente].count > maxMensajesPermitidos;
}

function guardarMensajeDB(nombre, telefono, contenido) {
    if (!contenido) return;
    
    const db = new sqlite3.Database(DB_NAME, (err) => {
        if (err) {
            console.error('Error al abrir la base de datos:', err.message);
            return;
        }
    });

    db.run(`
        CREATE TABLE IF NOT EXISTS mensajes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT,
            telefono TEXT,
            contenido TEXT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    `, (err) => {
        if (err) {
            console.error('Error al crear la tabla:', err.message);
            db.close();
            return;
        }

        db.run(
            `INSERT INTO mensajes (nombre, telefono, contenido) VALUES (?, ?, ?)`,
            [nombre, telefono, contenido],
            function(err) {
                if (err) {
                    console.error('Error al guardar mensaje en SQLite:', err.message);
                } else {
                    console.log(`[BD OK] Mensaje guardado de: ${nombre} (${telefono})`);
                }
                db.close();
            }
        );
    });
}

async function connectToWhatsApp() {
    console.log('Iniciando carga de credenciales de Baileys...');
    const { state, saveCreds } = await useMultiFileAuthState('auth_info_baileys');

    console.log('Creando socket de conexión...');
    const sock = makeWASocket({
        logger: pino({ level: 'fatal' }),
        auth: state
    });

    sock.ev.on('connection.update', (update) => {
        const { connection, lastDisconnect, qr } = update;
        if (qr) {
            console.log('¡QR Generado con éxito! Escanéalo:');
            qrcode.generate(qr, { small: true });
        }
        if (connection === 'close') {
            const shouldReconnect = (lastDisconnect?.error)?.output?.statusCode !== DisconnectReason.loggedOut;
            console.log('Conexión cerrada. ¿Reconectar?', shouldReconnect);
            if (shouldReconnect) {
                connectToWhatsApp();
            }
        } else if (connection === 'open') {
            console.log('¡Conectado a WhatsApp exitosamente!');
        }
    });

    sock.ev.on('creds.update', saveCreds);

    sock.ev.on('messages.upsert', async ({ messages }) => {
        const m = messages[0];
        if (!m.message || m.key.fromMe) return;

        const remoteJid = m.key.remoteJid;
        
        let telefono = '';
        if (remoteJid.endsWith('@s.whatsapp.net')) {
            telefono = remoteJid.split('@')[0]; // Extrae el número de teléfono limpio y real
        } else if (remoteJid.includes('@lid')) {
            telefono = 'Dispositivo Vinculado (LID)';
        } else {
            telefono = remoteJid.split('@')[0];
        }

        const nombre = m.pushName || 'Desconocido';
        const messageContent = m.message.conversation || m.message.extendedTextMessage?.text;

        if (messageContent) {
            console.log(`Mensaje recibido de ${nombre} (${telefono}): ${messageContent}`);
            
            if (esSpam(telefono, messageContent)) {
                console.log(`[SPAM BLOCKED] Mensaje bloqueado de ${telefono}`);
                return; 
            }

            guardarMensajeDB(nombre, telefono, messageContent);
        }
    });
}

console.log('Llamando a connectToWhatsApp()...');
connectToWhatsApp();