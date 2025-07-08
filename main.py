import httpx
import json
import os
from contextlib import asynccontextmanager
from http import HTTPStatus
from dotenv import load_dotenv
from fastapi import FastAPI, Request, Response
from telegram import Update
from telegram.ext import Application, ContextTypes, CommandHandler, MessageHandler, filters

# Load environment variables
load_dotenv()
TELEGRAM_BOT_TOKEN: str = os.getenv('TELEGRAM_BOT_TOKEN')
WEBHOOK_DOMAIN: str = os.getenv('RAILWAY_PUBLIC_DOMAIN')

# Build the Telegram Bot application
bot_builder = (
    Application.builder()
    .token(TELEGRAM_BOT_TOKEN)
    .updater(None)
    .build()
)


@asynccontextmanager
async def lifespan(_: FastAPI):
    """ Sets the webhook for the Telegram Bot and manages its lifecycle (start/stop). """
    await bot_builder.bot.setWebhook(url=WEBHOOK_DOMAIN)
    async with bot_builder:
        await bot_builder.start()
        yield
        await bot_builder.stop()


app = FastAPI(lifespan=lifespan)


@app.post("/")
async def process_update(request: Request):
    """ Handles incoming Telegram updates and processes them with the bot. """
    message = await request.json()
    update = Update.de_json(data=message, bot=bot_builder.bot)
    await bot_builder.process_update(update)
    return Response(status_code=HTTPStatus.OK)


async def start(update: Update, _: ContextTypes.DEFAULT_TYPE) -> None:
    """ Обрабатывает команду /start """
    reply = "Привет, брат 👋 Я готов к бою!\n\nДоступные команды:\n" \
            "/портфель — показать активы\n" \
            "/рынок — анализ ситуации\n" \
            "/нфт — NFT-пульс"
    await update.message.reply_text(reply)


async def portfolio(update: Update, _: ContextTypes.DEFAULT_TYPE) -> None:
    """ Показывает портфель инвестиций """
    try:
        with open("portfolio.json", "r") as f:
            data = json.load(f)

        reply = "📊 Портфель:\n"
        for key, info in data.items():
            if key == "USDT":
                reply += f"USDT (Bybit): ${info['amount']} — стейкинг {info['staking']}%\n"
            elif key == "NFT":
                reply += f"NFT: 🎴 {info['name']} (вход: {info['buy_floor_sol']} SOL)\n"
            else:
                reply += f"{key}: {info['amount']} — куплено на ${info['buy_usd']}\n"

        await update.message.reply_text(reply)
    except Exception as e:
        await update.message.reply_text("Ошибка при чтении портфеля.")


async def get_prices():
    url = "https://pro-api.coinmarketcap.com/v1/cryptocurrency/quotes/latest"
    headers = {
        "Accepts": "application/json",
        "X-CMC_PRO_API_KEY": os.getenv("COINMARKETCAP_API_KEY")
    }
    symbols = ["BTC", "ETH", "SOL", "ARB", "TON"]
    params = {
        "symbol": ",".join(symbols),
        "convert": "USD"
    }

    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(url, params=params, headers=headers)
            response.raise_for_status()
            data = response.json()["data"]

            return {
                "BTC": round(data["BTC"]["quote"]["USD"]["price"], 2),
                "ETH": round(data["ETH"]["quote"]["USD"]["price"], 2),
                "SOL": round(data["SOL"]["quote"]["USD"]["price"], 2),
                "ARB": round(data["ARB"]["quote"]["USD"]["price"], 2),
                "TON": round(data["TON"]["quote"]["USD"]["price"], 2),
            }
    except Exception as e:
        print(f"Ошибка в get_prices: {e}")
        return None

def calculate_profit(prices, portfolio):
    result = []
    for token, info in portfolio.items():
        if token not in prices:
            continue
        current_price = prices[token]
        buy_price = info["buy_usd"]
        percent = round(((current_price - buy_price) / buy_price) * 100, 2)
        arrow = "📈" if percent > 0 else "📉"
        result.append(f"{token}: {percent:+.2f}% {arrow}")
    return result



async def market(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Показывает текущие цены на основные активы"""
    prices = await get_prices()
    if prices:
        reply = (
            f"📊 Актуальные курсы:\n"
            f"BTC: ${prices['BTC']}\n"
            f"ETH: ${prices['ETH']}\n"
            f"SOL: ${prices['SOL']}\n"
            f"ARB: ${prices['ARB']}\n"
            f"TON: ${prices['TON']}"
        )
    else:
        reply = "❌ Не удалось получить цены с CoinGecko."

    await update.message.reply_text(reply)

async def profit(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        with open("portfolio.json", "r") as f:
            portfolio = json.load(f)

        prices = await get_prices()

        if not prices:
            await update.message.reply_text("❌ Не удалось получить цены.")
            return

        lines = calculate_profit(prices, portfolio)
        reply = "💰 Доходность портфеля:\n\n" + "\n".join(lines)
        await update.message.reply_text(reply)

    except Exception as e:
        await update.message.reply_text("⚠️ Ошибка при расчёте доходности.")
        print(f"Ошибка в /доход: {e}")



async def echo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = update.message.text.lower()

    if text == "/портфель":
        await portfolio(update, context)
    elif text == "/рынок":
         await market(update, context)
    elif text == "/профит":
         await profit(update, context)
    elif text == "/нфт":
        await update.message.reply_text("🖼 NFT-пульс: VALA в портфеле. Следим за Rogues Dead")
    else:
        reply = "🤔 Брат, не понял 🧠 Попробуй: /портфель, /рынок или /нфт"
        await update.message.reply_text(reply)




bot_builder.add_handler(CommandHandler(command="start", callback=start))
bot_builder.add_handler(CommandHandler("portfolio", portfolio))
bot_builder.add_handler(CommandHandler("market", market))
bot_builder.add_handler(CommandHandler("profit", profit))
bot_builder.add_handler(MessageHandler(filters=filters.TEXT & ~filters.COMMAND, callback=echo))
