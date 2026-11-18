import time
import csv
import os
from datetime import datetime, timezone

import ccxt
import pandas as pd

# =====================================
# CONFIGURACION GENERAL
# =====================================

SYMBOL = "BTC/USDT"

TIMEFRAME_TREND = "15m"
TIMEFRAME_ENTRY = "5m"

INITIAL_BALANCE = 1000.0
RISK_PERCENT = 0.01

STOP_LOSS_PERCENT = 0.02
TAKE_PROFIT_PERCENT = 0.04

MAX_POSITION_PERCENT = 0.50

TRADE_HISTORY = "trades.csv"

# =====================================
# BINANCE: SOLO CONSULTA PUBLICA
# =====================================

exchange = ccxt.binance({
    "enableRateLimit": True
})

# =====================================
# CARTERA SIMULADA
# =====================================

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
            "timestamp", "open", "high",
            "low", "close", "volume"
        ]
    )

    df["ema20"] = df["close"].ewm(
        span=20, adjust=False
    ).mean()

    df["ema50"] = df["close"].ewm(
        span=50, adjust=False
    ).mean()

    return df


# =====================================
# HISTORIAL
# =====================================

def save_trade(action, price, amount, profit=0):

    exists = os.path.exists(TRADE_HISTORY)

    with open(
        TRADE_HISTORY,
        "a",
        newline="",
        encoding="utf-8"
    ) as file:

        writer = csv.writer(file)

        if not exists:
            writer.writerow([
                "fecha", "accion",
                "precio", "cantidad_btc",
                "resultado_usdt"
            ])

        writer.writerow([
            datetime.now(timezone.utc).isoformat(),
            action,
            round(price, 2),
            round(amount, 8),
            round(profit, 2)
        ])


# =====================================
# ANALISIS DEL MERCADO
# =====================================

def analyze_market():

    trend = get_data(TIMEFRAME_TREND)
    entry = get_data(TIMEFRAME_ENTRY)

    # Ultima vela cerrada
    trend_candle = trend.iloc[-2]
    entry_candle = entry.iloc[-2]

    bullish = (
        trend_candle["ema20"] >
        trend_candle["ema50"]
    )

    bearish = (
        trend_candle["ema20"] <
        trend_candle["ema50"]
    )

    entry_signal = (
        entry_candle["ema20"] >
        entry_candle["ema50"]
    )

    if bullish and entry_signal:
        return "BUY", float(entry_candle["close"])

    if bearish:
        return "SELL", float(entry_candle["close"])

    return "HOLD", float(entry_candle["close"])


# =====================================
# ABRIR OPERACION SIMULADA
# =====================================

def open_position(price):

    global balance, btc_balance, position

    risk_amount = balance * RISK_PERCENT

    stop_distance = price * STOP_LOSS_PERCENT

    btc_amount = risk_amount / stop_distance

    # Limitar el capital comprometido
    max_cost = balance * MAX_POSITION_PERCENT

    btc_amount = min(
        btc_amount,
        max_cost / price
    )

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

    save_trade("BUY", price, btc_amount)

    print(f"COMPRA SIMULADA: {price:.2f}")
    print(f"BTC adquirido: {btc_amount:.8f}")


# =====================================
# CERRAR OPERACION SIMULADA
# =====================================

def close_position(price):

    global balance, btc_balance, position

    if position is None:
        return

    amount = position["amount"]

    balance += amount * price

    profit = amount * (
        price - position["entry"]
    )

    btc_balance -= amount

    save_trade("SELL", price, amount, profit)

    print(f"VENTA SIMULADA: {price:.2f}")
    print(f"Resultado: {profit:.2f} USDT")

    position = None


# =====================================
# EJECUCION PRINCIPAL
# =====================================

def run_bot():

    print("=" * 40)
    print("AGENTE BTC - PAPER TRADING")
    print("BINANCE - SOLO CONSULTA PUBLICA")
    print("=" * 40)

    print(f"Capital inicial: {INITIAL_BALANCE} USDT")

    while True:

        try:

            signal, price = analyze_market()

            print(f"\nBTC: {price:.2f}")
            print(f"Senal: {signal}")

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

            print(f"USDT disponible: {balance:.2f}")
            print(f"BTC: {btc_balance:.8f}")
            print(f"Capital total: {equity:.2f}")

            time.sleep(60)

        except Exception as error:

            print(f"ERROR: {error}")
            time.sleep(30)


if __name__ == "__main__":
    run_bot()
