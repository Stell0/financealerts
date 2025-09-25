import yfinance as yf
from datetime import datetime, timedelta

def retrieve_daily_prices(ticker, period = None, start=None, end=None):
    # set period to 14 days if not specified
    if period is None:
        period = 14

    # set start to today - period if not specified
    if start is None:
        start = datetime.today() - timedelta(days=period)

    # set end to today if not specified
    if end is None:
        end = datetime.today()

    df = yf.download(ticker, start, end, progress=False, auto_adjust=True)

    return df

def retrieve_hourly_prices(ticker, period = None, start=None, end=None):
    # set period to 14 days if not specified
    if period is None:
        period = 14

    # set start to today - period if not specified
    if start is None:
        start = datetime.today() - timedelta(days=period)

    # set end to today if not specified
    if end is None:
        end = datetime.today()

    df = yf.download(ticker, start, end, interval='1h',progress=False)
    return df

def get_next_earnings_date(ticker):
	stock = yf.Ticker(ticker)
	return stock.earnings_dates