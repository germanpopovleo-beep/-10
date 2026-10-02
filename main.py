import os
import re
import json
import math
import datetime
import logging
import httpx
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters
)

BOT_TOKEN = os.environ.get("BOT_TOKEN")

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

def get_weather(city: str = "Якутск") -> str:
    city_clean = str(city).lower().strip()
    fake_db = {
        "москва": "в Москве сейчас +15°C, облачно",
        "якутск": "в Якутске сейчас +5°C, ясно",
        "париж": "в Париже сейчас +18°C, небольшой дождь"
    }
    return fake_db.get(city_clean, f"в городе {city} сейчас +20°C, солнечно")

def get_time(timezone: str = "UTC") -> str:
    now = datetime.datetime.now(datetime.timezone.utc)
    return f"Текущее время (UTC): {now.strftime('%H:%M:%S')}"

def calculate(expression: str = "0") -> str:
    try:
        allowed_names = {"sqrt": math.sqrt, "pow": math.pow, "pi": math.pi, "abs": abs}
        result = eval(expression, {"__builtins__": None}, allowed_names)
        return str(result)
    except Exception as e:
        return f"Ошибка вычисления: {e}"

TOOLS = {
    "get_weather": get_weather,
    "get_time": get_time,
    "calculate": calculate
}

def extract_json(text: str):
    if not text:
        return None

    cleaned = text.strip()
    cleaned = re.sub(r'^```(?:json)?|```$', '', cleaned, flags=re.MULTILINE).strip()
    cleaned = cleaned.replace('\\"', '"')

    try:
        data = json.loads(cleaned)
        if isinstance(data, dict) and "tool" in data:
            return data
    except Exception:
        pass

    start = cleaned.find('{')
    end = cleaned.rfind('}')
    if start != -1 and end != -1 and end > start:
        json_str = cleaned[start:end+1]
        try:
            data = json.loads(json_str)
            if isinstance(data, dict) and "tool" in data:
                return data
        except Exception:
            pass

    return None

SYSTEM_PROMPT = (
    "Ты — ИИ-ассистент с инструментами.\n"
    "Если пользователю нужно узнать погоду, время или посчитать что-то, верни ТОЛЬКО JSON-структуру вида:\n"
    '{"tool": "get_weather", "args": {"city": "якутск"}}\n'
    '{"tool": "get_time", "args": {"timezone": "UTC"}}\n'
    '{"tool": "calculate", "args": {"expression": "2+2"}}\n'
    "Если инструменты не требуются — отвечай простым текстом."
)

async def agent_process(user_query: str) -> str:
    try:
        full_prompt = f"{SYSTEM_PROMPT}\n\nЗапрос пользователя: {user_query}"
        async with httpx.AsyncClient(timeout=25.0) as client:
            response = await client.post(
                "https://text.pollinations.ai/",
                json={"messages": [{"role": "user", "content": full_prompt}], "model": "openai"}
            )
            if response.status_code == 200:
                raw_content = response.text or ""
                tool_call = extract_json(raw_content)

                if tool_call and tool_call.get("tool") in TOOLS:
                    tool_name = tool_call["tool"]
                    args = tool_call.get("args", {})
                    if not isinstance(args, dict):
                        args = {}
                    tool_result = TOOLS[tool_name](**args)
                    return f"Результат работы инструмента ({tool_name}): {tool_result}"

                if raw_content.strip():
                    return raw_content.strip()
    except Exception as e:
        logging.error(f"Ошибка LLM: {e}")

    return "Не удалось получить ответ от сервиса. Попробуйте еще раз."

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Здарова! Я облачный бот с инструментами. Задавай вопросы!")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_text = update.message.text
    final_answer = await agent_process(user_text)
    await update.message.reply_text(final_answer)

if __name__ == '__main__':
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    print("Бот запущен на Render!")
    app.run_polling()