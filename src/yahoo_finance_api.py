import yfinance as yf
import pandas as pd
import os
from datetime import datetime, timedelta

def _sanitize_ticker_filename(ticker):
    """Sanitize ticker name for use as filename"""
    return ticker.replace('/', '_').replace('\\', '_').replace(':', '_').replace('*', '_').replace('?', '_').replace('"', '_').replace('<', '_').replace('>', '_').replace('|', '_')

def retrieve_daily_prices(ticker, period = None, start=None, end=None):
    # Sanitize ticker for filename
    safe_ticker = _sanitize_ticker_filename(ticker)
    cache_file = f'data/{safe_ticker}.csv'

    # Check for existing cache
    if os.path.exists(cache_file):
        try:
            # Load cached data
            cached_df = pd.read_csv(cache_file, index_col=0, parse_dates=True)
            
            # Check if it is the bad format (MultiIndex header saved) or valid data
            if not cached_df.empty:
                # If index contains "Ticker" or strings that shouldn't be dates, it might be the bad format
                # However, with parse_dates=True, if it failed to parse, the index might be object.
                # If it parsed successfully, index should be DatetimeIndex.
                if not isinstance(cached_df.index, pd.DatetimeIndex):
                    # Attempt to handle bad format or just discard
                    print(f"Warning: Cache for {ticker} seems corrupted or in old format. Ignoring.")
                    cached_df = pd.DataFrame() 
                else:
                    # remove the last value (row)
                    cached_df = cached_df.iloc[:-1]
                    
                    if not cached_df.empty:
                        last_date = cached_df.index[-1].date()
                        today = datetime.today().date()
                        
                        # Download data from last value to today
                        if last_date < today:
                            # Download from last_date (overlap is fine/safer to ensure continuity)
                            # User said "from last value to today"
                            fetch_start = last_date
                            fetch_end = today + timedelta(days=1) # end is exclusive usually in yfinance, or just use today()
                            
                            new_df = yf.download(ticker, start=fetch_start, end=fetch_end, progress=False, auto_adjust=True)
                            
                            # Flatten columns if MultiIndex
                            if isinstance(new_df.columns, pd.MultiIndex):
                                new_df.columns = new_df.columns.get_level_values(0)
                            
                            if not new_df.empty:
                                combined_df = pd.concat([cached_df, new_df])
                                # Remove duplicates based on index (date)
                                combined_df = combined_df[~combined_df.index.duplicated(keep='last')]
                                combined_df.to_csv(cache_file)
                                return combined_df
                        
                        return cached_df
            
        except Exception as e:
            print(f"Warning: Could not load cache for {ticker}: {e}. Fetching fresh data.")
            # Fall through to fetch fresh data

    # Fallback / No Cache logic
    # "otherwise, download last year of data" if not specified
    if start is None and period is None:
        start = datetime.today() - timedelta(days=365)
    elif period is not None and start is None:
        # If period is provided (e.g. "1y" or int 14), calculate start? 
        # yf.download handles 'period' argument if start is not provided.
        # But original code calculated start from period.
        if isinstance(period, int):
             start = datetime.today() - timedelta(days=period)
             period = None # Use calculated start
        # else let yf handle period string
    
    if end is None:
        end = datetime.today()

    # Download
    df = yf.download(ticker, start=start, end=end, period=period, progress=False, auto_adjust=True)

    # Flatten columns if MultiIndex
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    # Save to cache
    if not df.empty:
        df.to_csv(cache_file)


    # Save to cache
    if not df.empty:
        df.to_csv(cache_file)

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
