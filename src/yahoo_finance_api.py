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

    df = yf.download(ticker, start, end, progress=False)

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