import yahoo_finance_api
import indicators
import telegram_alert
import signals
import os, sys
import datetime
import re
import yfinance as yf
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(filename)s:%(lineno)d - %(message)s")

def load_tickers(file_path):
	with open(file_path, 'r') as file:
		tickers = [line.strip() for line in file if line.strip()]
	return tickers

def escape_markdown_v2(text):
	# List of MarkdownV2 special characters that need escaping
	special_chars = r"_*[]()~`>#+-=|{}.!"

	# Use a regular expression to escape each special character with a backslash
	escaped_text = re.sub(rf"([{re.escape(special_chars)}])", r"\\\1", str(text))
	return escaped_text

def main():
	# load ticker from argv if available
	if len(sys.argv) > 1:
		tickers = [sys.argv[1]]
	# load tickers from environment
	else:
		ticker_list = os.environ.get("TICKER_LIST")
		tickers = ticker_list.split()

	report = {}
	# initialize signal column with 0
	for ticker in tickers:
		try:
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
			if os.environ.get("INDICATORS") == None or "RSI" in os.environ.get("INDICATORS"):
				print("RSI")
				df = signals.rsi(df)
			if os.environ.get("INDICATORS") != None and "SMA" in os.environ.get("INDICATORS"):
				df = signals.sma(df,label="SMA200")
			df = signals.movingAverageCrossover(df,short='SMA50',long='SMA200')
			if os.environ.get("INDICATORS") != None and "MACD" in os.environ.get("INDICATORS"):
				df = signals.macd(df)
			if os.environ.get("INDICATORS") != None and "BB" in os.environ.get("INDICATORS"):
				df = signals.bb(df)

			# don't send aler if signal date is not today
			if df.index[-1].strftime('%Y-%m-%d') == datetime.datetime.now(datetime.UTC).strftime('%Y-%m-%d'):
				# send telegram alert if last signal is not 0
				if df.iloc[-1]['signal'].iloc[0] != 0:
					if df.iloc[-1]['signal'].iloc[0] > 0:
						signal = "BUY"
					if df.iloc[-1]['signal'].iloc[0] < 0:
						signal = "SELL"
					if not signal in report:
						report[signal] = {}
					#remove trailing comma from reason
					reason = re.sub (r",$", "", df.iloc[-1]['reason'].iloc[0])
					report[signal][ticker] = {"signal":signal,"strength":df.iloc[-1]['signal'].iloc[0],"reason":reason}
		except Exception as e:
			logging.exception(f"Error processing ticker {ticker}")
			continue

	# create the final report
	report_text = ""
	for signal in report:
		report_text += f"*{signal}:*\n"
		for ticker in report[signal]:
			if ".L" in ticker:
				url = f"https://www.tradingview.com/chart/gtgkesnl/?symbol=LSE%3A{ticker}"
			elif ".AX" in ticker:
				url = f"https://www.tradingview.com/chart/gtgkesnl/?symbol=ASX%3A{ticker.replace('.AX','')}"
			elif "SSUN.VI" in ticker: # special case for SSUN.VI
				url = f"https://www.tradingview.com/chart/gtgkesnl/?symbol=GETTEX%3ASSU"
			elif ".VI" in ticker:
				url = f"https://www.tradingview.com/chart/gtgkesnl/?symbol=GETTEX%3A{ticker}"
			elif ".PA" in ticker:
				url = f"https://www.tradingview.com/chart/gtgkesnl/?symbol=EURONEXT%3A{ticker.replace('.PA','')}"
			elif ".HK" in ticker:
				url = f"https://www.tradingview.com/chart/gtgkesnl/?symbol=HKEX%3A{ticker.replace('.HK','')}"
			else:
				url = "https://www.tradingview.com/chart/gtgkesnl/?symbol=" + re.sub(r"-","",ticker)
			msg = f"[{escape_markdown_v2(ticker)}]({escape_markdown_v2(url)}) {escape_markdown_v2(report[signal][ticker]['reason'])}\n"
			report_text += msg
		report_text += "\n\n"

	if report_text != "":
		telegram_alert.send_alert(report_text)

if __name__ == "__main__":
	main()

