import yahoo_finance_api
import indicators
import telegram_alert
import signals
import os
import datetime
import re

def load_tickers(file_path):
    with open(file_path, 'r') as file:
        tickers = [line.strip() for line in file if line.strip()]
    return tickers

def main():
    tickers = load_tickers(os.path.abspath(os.path.dirname(__file__))+'/../config/tickers.txt')
    report = {}

    # initialize signal column with 0
    for ticker in tickers:
        print(ticker)
        df = yahoo_finance_api.retrieve_daily_prices(ticker,period=365)
        df = indicators.rsi(df)
        df = indicators.sma(df, timeperiod=200, label="SMA200")
        df = indicators.linearreg(df)
        df = indicators.sma(df, timeperiod=40, label="SMA50")
        df = indicators.macd(df)
        df = indicators.bb(df)
        
        df['signal'] = 0
        df['reason'] = ""
        df = signals.rsi(df)
        #df = signals.sma(df,label="SMA200")
        #df = signals.movingAverageCrossover(df,short='SMA50',long='SMA200')
        #df = signals.macd(df)
        df = signals.bb(df)
       
        # don't send aler if signal date is not today
        if df.index[-1].strftime('%Y-%m-%d') != datetime.datetime.utcnow().strftime('%Y-%m-%d'):
            continue

        # send telegram alert if last signal is not 0
        if df.iloc[-1]['signal'] != 0:
            if df.iloc[-1]['signal'] > 0:
                signal = "BUY"
            if df.iloc[-1]['signal'] < 0:
                signal = "SELL"
            if not signal in report:
                report[signal] = {}
            
            #remove trailing comma from reason
            reason = re.sub (r",$", "", df.iloc[-1]['reason'])
            report[signal][ticker] = {"signal":signal,"strength":df.iloc[-1]['signal'],"reason":reason}

    # create the final report
    report_text = ""
    for signal in report:
        report_text += f"{signal}:\n"
        for ticker in report[signal]:
            if ".L" in ticker:
                url = f"https://www.tradingview.com/chart/gtgkesnl/?symbol=LSE%3A{ticker}"
            else:
                url = "https://www.tradingview.com/chart/gtgkesnl/?symbol=" + re.sub(r"-","",ticker)
            msg = f"{ticker} [{report[signal][ticker]['strength']}] {report[signal][ticker]['reason']} {url}\n"
            report_text += msg
        report_text += "\n"

    if report_text != "":
        telegram_alert.send_alert(report_text)



if __name__ == "__main__":
    main()

