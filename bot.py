import os
import psycopg

from openai import OpenAI
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import PlainTextResponse, Response
from starlette.routing import Route
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)


TOKEN = os.getenv("TOKEN")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
PORT = int(os.getenv("PORT", "10000"))
RENDER_EXTERNAL_URL = os.getenv("RENDER_EXTERNAL_URL")

client = OpenAI(
    api_key=OPENROUTER_API_KEY,
    base_url="https://openrouter.ai/api/v1",
)

DATABASE_URL = os.getenv("DATABASE_URL")

telegram_app = Application.builder().token(TOKEN).build()

def init_db():
    with psycopg.connect(DATABASE_URL) as conn:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS messages (
                    id SERIAL PRIMARY KEY,
                    user_id BIGINT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
        conn.commit()


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_memory[user_id] = []

    await update.message.reply_text(
        "Привет! 👋 Я твой AI-помощник.\n"
        "Я буду помнить контекст нашего разговора."
    )


async def message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text

    with psycopg.connect(DATABASE_URL) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO messages (user_id, role, content)
                VALUES (%s, %s, %s)
                """,
                (user_id, "user", text),
            )

            cur.execute(
                """
                SELECT role, content
                FROM messages
                WHERE user_id = %s
                ORDER BY id DESC
                LIMIT 20
                """,
                (user_id,),
            )

            history = cur.fetchall()

        conn.commit()

    history.reverse()

    messages = [
        {
            "role": "system",
            "content": (
                "Ты полезный личный AI-помощник. "
                "Учитывай предыдущие сообщения пользователя "
                "в этом разговоре."
            ),
        }
    ]

    messages.extend(
        {
            "role": role,
            "content": content,
        }
        for role, content in history
    )

    response = client.chat.completions.create(
        model="openrouter/free",
        messages=messages,
    )

    answer = response.choices[0].message.content

    with psycopg.connect(DATABASE_URL) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO messages (user_id, role, content)
                VALUES (%s, %s, %s)
                """,
                (user_id, "assistant", answer),
            )
        conn.commit()

    await update.message.reply_text(answer)


telegram_app.add_handler(CommandHandler("start", start))
telegram_app.add_handler(
    MessageHandler(filters.TEXT & ~filters.COMMAND, message)
)


async def health(request: Request):
    return PlainTextResponse("OK")


async def telegram_webhook(request: Request):
    data = await request.json()
    update = Update.de_json(data, telegram_app.bot)

    await telegram_app.process_update(update)

    return Response(status_code=200)


async def startup():
    init_db()
    await telegram_app.initialize()
    await telegram_app.start()

    if RENDER_EXTERNAL_URL:
        await telegram_app.bot.set_webhook(
            url=f"{RENDER_EXTERNAL_URL}/telegram"
        )


async def shutdown():
    if telegram_app.bot:
        await telegram_app.bot.delete_webhook()

    await telegram_app.stop()
    await telegram_app.shutdown()

routes = [
    Route("/", health),
    Route("/health", health),
    Route("/telegram", telegram_webhook, methods=["POST"]),
]
from contextlib import asynccontextmanager


@asynccontextmanager
async def lifespan(app):
    await startup()
    yield
    await shutdown()
    
app = Starlette(routes=routes, lifespan=lifespan)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        app,
        host="0.0.0.0",
        port=PORT,
    )