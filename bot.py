import os
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters
from openai import OpenAI

TOKEN = os.getenv("TOKEN")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")

client = OpenAI(
    api_key=OPENROUTER_API_KEY,
    base_url="https://openrouter.ai/api/v1"
)

# Память разговоров
user_memory = {}


async def message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text

    # Создаём память для нового пользователя
    if user_id not in user_memory:
        user_memory[user_id] = []

    # Добавляем сообщение пользователя в память
    user_memory[user_id].append({
        "role": "user",
        "content": text
    })

    # Отправляем запрос ИИ вместе с предыдущими сообщениями
    response = client.chat.completions.create(
        model="openrouter/free",
        messages=[
            {
                "role": "system",
                "content": "Ты полезный личный AI-помощник. Учитывай предыдущие сообщения пользователя в этом разговоре."
            },
            *user_memory[user_id]
        ]
    )

    answer = response.choices[0].message.content

    # Сохраняем ответ ИИ в память
    user_memory[user_id].append({
        "role": "assistant",
        "content": answer
    })

    await update.message.reply_text(answer)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    # Начать новый разговор
    user_memory[user_id] = []

    await update.message.reply_text(
        "Привет! 👋 Я твой AI-помощник.\n"
        "Я буду помнить контекст нашего разговора."
    )


app = Application.builder().token(TOKEN).build()

app.add_handler(CommandHandler("start", start))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message))

print("Бот запущен!")
app.run_polling()