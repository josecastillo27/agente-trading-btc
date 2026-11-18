trading_bot.py
""" AGENTE TRADING BTC
Binance - Paper Trading
Estrategia EMA 20 / EMA 50
"""

import time
import pandas as pd
import ccxt

# CONFIGURACIÓN
SYMBOL = "BTC/USDT"
TIMEFRAME_TREND = "15m"
TIMEFRAME_ENTRY = "5m"

INITIAL_BALANCE = 1000.0
RISK_PERCENT = 0.01

STOP_LOSS_PERCENT = 0.02
TAKE_PROFIT_PERCENT = 0.04

# CONEXIÓN PÚBLICA A BINANCE
exchange = ccxt.binance({
    "enableRateLimit": True
})

# CARTERA SIMULADA
balance = INITIAL_BALANCE
btc_balance = 0.0
position = None


def get_data(timeframe):

    candles = exchange.fetch_ohlcv(
        SYMBOL,
        timeframe=timeframe,
        limit=100
    )

    df = pd.DataFrame(
        candles,
        columns=[
            "timestamp",
            "open",
            "high",
            "low",
            "close",
            "volume"
        ]
    )

    df["ema20"] = df["close"].ewm(
        span=20,
        adjust=False
    ).mean()

    df["ema50"] = df["close"].ewm(
        span=50,
        adjust=False
    ).mean()

    return df


def analyze_market():

    trend = get_data(TIMEFRAME_TREND)
    entry = get_data(TIMEFRAME_ENTRY)

    last_trend = trend.iloc[-2]
    last_entry = entry.iloc[-2]

    bullish = (
        last_trend["ema20"] > last_trend["ema50"]
    )

    bearish = (
        last_trend["ema20"] < last_trend["ema50"]
    )

    entry_signal = (
        last_entry["ema20"] > last_entry["ema50"]
    )

    if bullish and entry_signal:
        return "BUY", float(last_entry["close"])

    if bearish:
        return "SELL", float(last_entry["close"])

    return "HOLD", float(last_entry["close"])


def open_position(price):

    global balance, btc_balance, position

    risk_amount = balance * RISK_PERCENT

    stop_distance = price * STOP_LOSS_PERCENT

    btc_amount = risk_amount / stop_distance

    cost = btc_amount * price

    if cost > balance:
        btc_amount = balance / price
        cost = btc_amount * price

    if btc_amount <= 0:
        return

    balance -= cost
    btc_balance += btc_amount

    position = {
        "entry": price,
        "amount": btc_amount,
        "stop": price * (1 - STOP_LOSS_PERCENT),
        "target": price * (1 + TAKE_PROFIT_PERCENT)
    }

    print(f"COMPRA SIMULADA: {price:.2f}")


def close_position(price):

    global balance, btc_balance, position

    if position is None:
        return

    amount = position["amount"]

    balance += amount * price

    profit = amount * (price - position["entry"])

    btc_balance -= amount
    position = None

    print(f"VENTA SIMULADA: {price:.2f}")
    print(f"Resultado: {profit:.2f} USDT")


def run_bot():

    global position

    print("AGENTE BTC INICIADO")
    print("MODO PAPER TRADING")
    print(f"Capital virtual: {INITIAL_BALANCE} USDT")

    while True:

        try:

            signal, price = analyze_market()

            print(
                f"BTC: {price:.2f} | "
                f"Señal: {signal}"
            )

            if position is None:

                if signal == "BUY":
                    open_position(price)

            else:

                if (
                    price <= position["stop"]
                    or price >= position["target"]
                    or signal == "SELL"
                ):
                    close_position(price)

            equity = balance + btc_balance * price

            print(f"Capital total: {equity:.2f} USDT")
            print("-" * 40)

            time.sleep(60)

        except Exception as error:

            print(f"Error: {error}")
            time.sleep(30)


if __name__ == "__main__":
    run_bot()
