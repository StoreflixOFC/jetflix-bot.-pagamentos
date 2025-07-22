
import os
import json
import requests
from datetime import datetime, timedelta
import telebot
from telebot import types
from flask import Flask, request
import threading

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
MP_ACCESS_TOKEN = os.getenv("MP_ACCESS_TOKEN")

if not TOKEN or not MP_ACCESS_TOKEN:
    raise Exception("❌ ERRO: Os tokens do Telegram ou Mercado Pago não estão configurados corretamente.")

bot = telebot.TeleBot(TOKEN)
ADMIN_ID = 7730543432
ARQUIVO_USUARIOS = 'usuarios.txt'

def carregar_usuarios():
    if not os.path.exists(ARQUIVO_USUARIOS):
        return {}
    with open(ARQUIVO_USUARIOS, 'r') as f:
        return json.load(f)

def salvar_usuarios(dados):
    with open(ARQUIVO_USUARIOS, 'w') as f:
        json.dump(dados, f)

def acesso_valido(user_id):
    usuarios = carregar_usuarios()
    data_exp = usuarios.get(str(user_id))
    if not data_exp:
        return False
    return datetime.now().date() <= datetime.strptime(data_exp, "%Y-%m-%d").date()

PLANOS = {
    "mensal": {"titulo": "Mensal", "preco": 19.90, "dias": 30},
    "trimestral": {"titulo": "Trimestral", "preco": 49.90, "dias": 90},
    "anual": {"titulo": "Anual", "preco": 99.90, "dias": 365}
}

@bot.message_handler(commands=['comprar'])
def comprar(message):
    markup = types.InlineKeyboardMarkup()
    for plano in PLANOS:
        markup.add(types.InlineKeyboardButton(
            text=f"{PLANOS[plano]['titulo']} - R${PLANOS[plano]['preco']}",
            callback_data=f"comprar_{plano}"
        ))
    bot.send_message(message.chat.id, "💳 *Escolha um plano para ativar seu acesso:*", reply_markup=markup, parse_mode='Markdown')

def gerar_link_pagamento(user_id, plano):
    info = PLANOS[plano]
    url = "https://api.mercadopago.com/checkout/preferences"
    headers = {"Authorization": f"Bearer {MP_ACCESS_TOKEN}"}
    payload = {
        "items": [{
            "title": f"Plano {info['titulo']} - Jetflix",
            "quantity": 1,
            "currency_id": "BRL",
            "unit_price": float(info['preco'])
        }],
        "notification_url": "https://SEU_DOMINIO/webhook",
        "external_reference": f"{user_id}:{plano}"
    }
    response = requests.post(url, headers=headers, json=payload)
    return response.json().get("init_point")

@bot.callback_query_handler(func=lambda call: call.data.startswith("comprar_"))
def tratar_pagamento(call):
    plano = call.data.split("_")[1]
    user_id = call.from_user.id
    link = gerar_link_pagamento(user_id, plano)
    bot.send_message(call.message.chat.id, f"🧾 Clique para pagar:
{link}

Aceitamos *Pix, cartão e boleto*.", parse_mode='Markdown')

@bot.message_handler(commands=['confirmar'])
def confirmar_pagamento(message):
    if message.from_user.id != ADMIN_ID:
        return
    try:
        _, user_id, plano = message.text.split()
        if plano not in PLANOS:
            raise Exception()
        usuarios = carregar_usuarios()
        dias = PLANOS[plano]["dias"]
        nova_data = (datetime.now() + timedelta(days=dias)).strftime("%Y-%m-%d")
        usuarios[user_id] = nova_data
        salvar_usuarios(usuarios)
        bot.send_message(message.chat.id, f"✅ Acesso liberado para {user_id} até {nova_data}.", parse_mode="Markdown")
    except:
        bot.send_message(message.chat.id, "⚠️ Uso: /confirmar <user_id> <mensal|trimestral|anual>")

@bot.message_handler(commands=['verusuarios'])
def ver_usuarios(message):
    if message.from_user.id != ADMIN_ID:
        return
    usuarios = carregar_usuarios()
    texto = "👥 *Usuários autorizados:*

" + "\n".join([f"🆔 {uid} - até {data}" for uid, data in usuarios.items()])
    bot.send_message(message.chat.id, texto, parse_mode='Markdown')

@bot.message_handler(commands=['start'])
def boas_vindas(message):
    if not acesso_valido(message.from_user.id):
        bot.send_message(message.chat.id, "🚫 Acesso não autorizado ou vencido.\nUse /comprar para ativar seu plano.")
        return
    markup = types.InlineKeyboardMarkup(row_width=2)
    botoes = [types.InlineKeyboardButton(text=nome, callback_data=comando) for nome, comando in [
        ("Apple TV", "/appletv"),
        ("YouTube", "/youtube"),
        ("Paramount", "/paramount"),
        ("Prime Vídeo", "/primevideo"),
        ("Grupo VIP WhatsApp", "/grupovip")
    ]]
    markup.add(*botoes)
    bot.send_message(message.chat.id, "🎉 *BEM-VINDO AO GERADOR DE STREAMING PREMIUM JETFLIX!*", reply_markup=markup, parse_mode='Markdown')

@bot.callback_query_handler(func=lambda call: True)
def callback(call):
    if not acesso_valido(call.from_user.id):
        bot.send_message(call.message.chat.id, "⛔ Seu acesso expirou ou não está autorizado.")
        return
    nome = call.data[1:]
    resposta = {
        "appletv": "🍏 *Apple TV*\nLogin: storeflix00@icloud.com\nSenha: Gcay1234",
        "youtube": "📺 *YouTube*\nLogin: storeflix9@gmail.com\nSenha: Gcay1234",
        "paramount": "🎞️ *Paramount+*\nLogin: storeflix9@gmail.com\nSenha: Gcay1234",
        "primevideo": "🎬 *Prime Vídeo*\nLogin: storeflix9@gmail.com ou telefone\nSenha: Gcay1234",
        "grupovip": "💬 *GRUPO VIP WHATSAPP*\n👉 [Clique aqui](https://chat.whatsapp.com/JWZeb7hkSF255MqmqPVRSW)"
    }.get(nome, "🔐 Serviço indisponível.")
    bot.send_message(call.message.chat.id, resposta, parse_mode='Markdown', disable_web_page_preview=True)

app = Flask(__name__)

@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.json
    if not data or data.get("type") != "payment":
        return "Ignored", 200
    payment_id = data["data"]["id"]
    headers = {"Authorization": f"Bearer {MP_ACCESS_TOKEN}"}
    r = requests.get(f"https://api.mercadopago.com/v1/payments/{payment_id}", headers=headers)
    pagamento = r.json()
    if pagamento.get("status") == "approved":
        ref = pagamento.get("external_reference")
        if ref and ":" in ref:
            user_id, plano = ref.split(":")
            usuarios = carregar_usuarios()
            dias = PLANOS[plano]["dias"]
            nova_data = (datetime.now() + timedelta(days=dias)).strftime("%Y-%m-%d")
            usuarios[user_id] = nova_data
            salvar_usuarios(usuarios)
            print(f"✅ Acesso ativado automaticamente para {user_id} via webhook.")
    return "ok", 200

def start_webhook():
    app.run(host="0.0.0.0", port=8000)

threading.Thread(target=start_webhook).start()
bot.polling(none_stop=True)
