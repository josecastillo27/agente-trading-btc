import time
import csv
import os
import json
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

# Costos simulados: ajustar a las condiciones
# reales de la cuenta y del exchange.
FEE_RATE = 0.001
SLIPPAGE_RATE = 0.0005

TRADE_HISTORY = "trades.csv"
STATE_FILE = "bot_state.json"

LOOP_SECONDS = 30

# =====================================
# BINANCE - SOLO CONSULTA PUBLICA
# =====================================

exchange = ccxt.binance({
    "enableRateLimit": True
})

# =====================================
# CARTERA
# =====================================

balance = INITIAL_BALANCE
btc_balance = 0.0
position = None
last_processed_candle = None


# =====================================
# PERSISTENCIA
# =====================================

def save_state():

    state = {
        "balance": balance,
        "btc_balance": btc_balance,
        "position": position,
        "last_processed_candle": last_processed_candle
    }

    temp_file = STATE_FILE + ".tmp"

    with open(temp_file, "w", encoding="utf-8") as file:
        json.dump(state, file, indent=4)

    os.replace(temp_file, STATE_FILE)


def load_state():

    global balance
    global btc_balance
    global position
    global last_processed_candle

    if not os.path.exists(STATE_FILE):
        save_state()
        return

    with open(STATE_FILE, "r", encoding="utf-8") as file:
        state = json.load(file)

    balance = float(state["balance"])
    btc_balance = float(state["btc_balance"])
    position = state["position"]
    last_processed_candle = state["last_processed_candle"]

    print("Estado anterior recuperado correctamente.")


# =====================================
# DATOS DE MERCADO
# =====================================

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

    if len(df) < 52:
        raise ValueError("Datos insuficientes para calcular EMA.")

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

def save_trade(
    action,
    price,
    amount,
    fee=0,
    profit=0,
    reason=""
):

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
                "fecha",
                "accion",
                "precio",
                "cantidad_btc",
                "comision_usdt",
                "resultado_neto_usdt",
                "motivo",
                "balance_usdt"
            ])

        writer.writerow([
            datetime.now(timezone.utc).isoformat(),
            action,
            round(price, 2),
            round(amount, 8),
            round(fee, 4),
            round(profit, 4),
            reason,
            round(balance, 2)
        ])


# =====================================
# ANALISIS DEL MERCADO
# =====================================

def analyze_market():

    trend = get_data(TIMEFRAME_TREND)
    entry = get_data(TIMEFRAME_ENTRY)

    # Ultimas velas completamente cerradas
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
        signal = "BUY"

    elif bearish:
        signal = "SELL"

    else:
        signal = "HOLD"

    return signal, entry_candle


# =====================================
# ABRIR POSICION
# =====================================

def open_position(price, candle_timestamp):

    global balance
    global btc_balance
    global position

    # Precio estimado de compra con deslizamiento
    entry_price = price * (1 + SLIPPAGE_RATE)

    equity = balance + btc_balance * price

    risk_amount = equity * RISK_PERCENT

    stop_price = entry_price * (
        1 - STOP_LOSS_PERCENT
    )

    target_price = entry_price * (
        1 + TAKE_PROFIT_PERCENT
    )

    # Perdida estimada por BTC incluyendo costos
    loss_per_btc = (
        entry_price - stop_price
        + entry_price * FEE_RATE
        + stop_price * (1 + SLIPPAGE_RATE) * FEE_RATE
    )

    if loss_per_btc <= 0:
        return

    btc_amount = risk_amount / loss_per_btc

    # Limitar exposicion maxima
    max_notional = balance * MAX_POSITION_PERCENT

    btc_amount = min(
        btc_amount,
        max_notional / entry_price,
        balance / (entry_price * (1 + FEE_RATE))
    )

    btc_amount = round(btc_amount, 8)

    if btc_amount <= 0:
        return

    cost = btc_amount * entry_price
    buy_fee = cost * FEE_RATE

    if cost + buy_fee > balance:
        return

    balance -= cost + buy_fee
    btc_balance += btc_amount

    position = {
        "entry": entry_price,
        "amount": btc_amount,
        "entry_fee": buy_fee,
        "stop": stop_price,
        "target": target_price,
        "candle_timestamp": int(candle_timestamp)
    }

    save_trade(
        "BUY",
        entry_price,
        btc_amount,
        fee=buy_fee,
        reason="EMA_SIGNAL"
    )

    save_state()

    print("\nCOMPRA SIMULADA")
    print(f"Precio: {entry_price:.2f}")
    print(f"BTC: {btc_amount:.8f}")
    print(f"Stop Loss: {stop_price:.2f}")
    print(f"Take Profit: {target_price:.2f}")


# =====================================
# CERRAR POSICION
# =====================================

def close_position(price, reason):

    global balance
    global btc_balance
    global position

    if position is None:
        return

    amount = position["amount"]

    # Precio estimado de venta con deslizamiento
    exit_price = price * (1 - SLIPPAGE_RATE)

    proceeds = amount * exit_price
    sell_fee = proceeds * FEE_RATE

    balance += proceeds - sell_fee

    profit = (
        proceeds
        - sell_fee
        - amount * position["entry"]
        - position["entry_fee"]
    )

    btc_balance -= amount

    save_trade(
        "SELL",
        exit_price,
        amount,
        fee=sell_fee,
        profit=profit,
        reason=reason
    )

    print("\nVENTA SIMULADA")
    print(f"Precio: {exit_price:.2f}")
    print(f"Resultado neto: {profit:.2f} USDT")
    print(f"Motivo: {reason}")

    position = None

    save_state()


# =====================================
# CONTROL DE STOP LOSS Y TAKE PROFIT
# =====================================

def check_position(candle, signal):

    if position is None:
        return

    timestamp = int(candle["timestamp"])

    # No usar la misma vela que genero la entrada
    if timestamp <= position["candle_timestamp"]:
        return

    stop = position["stop"]
    target = position["target"]

    low = float(candle["low"])
    high = float(candle["high"])
    open_price = float(candle["open"])

    # Si ambos niveles aparecen en la misma vela,
    # asumimos primero el Stop Loss (criterio conservador).

    if low <= stop:

        exit_price = min(open_price, stop)

        close_position(exit_price, "STOP_LOSS")

    elif high >= target:

        exit_price = max(open_price, target)

        close_position(exit_price, "TAKE_PROFIT")

    elif signal == "SELL":

        close_position(
            float(candle["close"]),
            "EMA_SELL_SIGNAL"
        )


# =====================================
# ESTADISTICAS
# =====================================

def show_account(price):

    equity = balance + btc_balance * price

    print("\n--- CARTERA SIMULADA ---")
    print(f"USDT disponible: {balance:.2f}")
    print(f"BTC disponible: {btc_balance:.8f}")
    print(f"Capital total: {equity:.2f}")
    print(
        f"Resultado total: "
        f"{equity - INITIAL_BALANCE:.2f} USDT"
    )

    if position:
        print(f"Stop: {position['stop']:.2f}")
        print(f"Target: {position['target']:.2f}")


# =====================================
# EJECUCION PRINCIPAL
# =====================================

def run_bot():

    print("=" * 45)
    print("AGENTE BTC - VERSION 2.0")
    print("PAPER TRADING")
    print("BINANCE - CONSULTA PUBLICA")
    print("=" * 45)

    load_state()

    while True:

        try:

            signal, candle = analyze_market()

            timestamp = int(candle["timestamp"])
            price = float(candle["close"])

            # Evitar procesar dos veces la misma vela
            if (
                last_processed_candle is not None
                and timestamp <= last_processed_candle
            ):
                time.sleep(LOOP_SECONDS)
                continue

            print("\n" + "=" * 35)
            print(f"BTC: {price:.2f}")
            print(f"Senal: {signal}")

            if position is None:

                if signal == "BUY":
                    open_position(price, timestamp)

            else:

                check_position(candle, signal)

            show_account(price)

            last_processed_candle = timestamp

            save_state()

            time.sleep(LOOP_SECONDS)

        except KeyboardInterrupt:

            print("\nBot detenido por el usuario.")
            save_state()
            break

        except Exception as error:

            print(f"\nERROR: {error}")
            time.sleep(30)


if __name__ == "__main__":
    run_bot()
