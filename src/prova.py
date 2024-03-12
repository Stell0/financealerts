import yfinance as yf
import math
import os

# Function to calculate individual indicator ratings
def calculate_indicator_rating(indicator_value, lower_bound, upper_bound):
    if lower_bound <= indicator_value <= upper_bound:
        return 10
    elif indicator_value < lower_bound:
        return 5 * (indicator_value / lower_bound)
    else:
        return 10 - 5 * (indicator_value - upper_bound) / (upper_bound - lower_bound)

def check_stock_criteria(ticker):
    # Retrieve financial data for the stock
    stock = yf.Ticker(ticker)
    
    #print(stock.info)

    # Get trailing PE ratio
    trailing_pe = stock.info['trailingPE'] if 'trailingPE' in stock.info else None

    # Get forward PE ratio
    forward_pe = stock.info['forwardPE'] if 'forwardPE' in stock.info else None

    # Get Debt to Equity ratio
    debt_to_equity = stock.info['debtToEquity'] if 'debtToEquity' in stock.info else None

    # Get EPS Growth
    eps_growth = stock.info['trailingEps'] / stock.info['forwardEps'] - 1 if 'trailingEps' in stock.info and 'forwardEps' in stock.info else None

    # Calculate PEG Ratio (Price to Earnings Growth)
    peg_ratio = stock.info['pegRatio'] if 'pegRatio' in stock.info else None

    # Get Market Cap
    market_cap = stock.info['marketCap'] if 'marketCap' in stock.info else None

    # Check if the stock meets the criteria
    if trailing_pe is not None and trailing_pe < 25:
        print (f'OK! Trailing PE is {trailing_pe} and should be < 25')
    else:
        print (f'NOPE! Trailing PE is {trailing_pe} and should be < 25')

    if forward_pe is not None and forward_pe < 15:
        print (f'OK! Forward PE is {forward_pe} and should be < 15')
    else:
        print (f'NOPE! Forward PE is {forward_pe} and should be < 15')

    if debt_to_equity is not None and debt_to_equity < 0.35:
        print (f'OK! Debt to Equity is {debt_to_equity} and should be < 0.35')
    else:
        print (f'NOPE! Debt to Equity is {debt_to_equity} and should be < 0.35')

    if eps_growth is not None and eps_growth > 0.15:
        print (f'OK! EPS Growth is {eps_growth} and should be > 0.15')
    else:
        print (f'NOPE! EPS Growth is {eps_growth} and should be > 0.15')
    
    if peg_ratio is not None and peg_ratio < 1.2:
        print (f'OK! PEG Ratio is {peg_ratio} and should be < 1.2')
    else:
        print (f'NOPE! PEG Ratio is {peg_ratio} and should be < 1.2')

    if market_cap is not None and market_cap < 5e9:
        print (f'OK! Market Cap is {market_cap} and should be < 5e9')
    else:
        print (f'NOPE! Market Cap is {market_cap} and should be < 5e9')


    # Financial indicators based on the JSON data
    current_ratio = stock.info.get('currentRatio', 0)
    quick_ratio = stock.info.get('quickRatio', 0)
    profit_margin = stock.info.get('profitMargins', 0)
    roe = stock.info.get('returnOnEquity', 0)
    roa = stock.info.get('returnOnAssets', 0)
    pe_ratio = stock.info.get('trailingPE', 0)
    ps_ratio = stock.info.get('priceToSalesTrailing12Months', 0)
    pb_ratio = stock.info.get('priceToBook', 0)
    debt_equity_ratio = stock.info.get('debtToEquity', 0)
    dividend_yield = stock.info.get('trailingAnnualDividendYield', 0)
    earnings_growth = stock.info.get('earningsQuarterlyGrowth', 0)

    # Define rating boundaries for each indicator (adjust as needed)
    indicator_ratings = {
        'currentRatio': (1.5, 3),
        'quickRatio': (1, 2),
        'profitMargin': (5, 15),
        'returnOnEquity': (10, 20),
        'returnOnAssets': (5, 15),
        'trailingPE': (5, 15),
        'priceToSalesTrailing12Months': (0, 5),
        'priceToBook': (0, 5),
        'debtToEquity': (0, 2),
        'trailingAnnualDividendYield': (0, 5),
        'earningsQuarterlyGrowth': (0, math.inf),
    }

    # Calculate ratings for each indicator
    indicator_ratings_result = {}
    for indicator, bounds in indicator_ratings.items():
        indicator_ratings_result[indicator] = calculate_indicator_rating(
            locals()[indicator],
            bounds[0],
            bounds[1]
        )

    # Calculate an overall rating as an average of all indicator ratings
    overall_rating = sum(indicator_ratings_result.values()) / len(indicator_ratings_result)

    # Display individual indicator ratings
    print("Individual Indicator Ratings:")
    for indicator, rating in indicator_ratings_result.items():
        print(f"{indicator}: {rating}/10")

    # Display the overall rating
    print(f"\nOverall Rating: {overall_rating}/10")

    meets_criteria = (
        (trailing_pe is not None and trailing_pe < 25) and
        (forward_pe is not None and forward_pe < 15) and
        (debt_to_equity is not None and debt_to_equity < 0.35) and
        (eps_growth is not None and eps_growth > 0.15) and
        (peg_ratio is not None and peg_ratio < 1.2) and
        (market_cap is not None and market_cap < 5e9)
    )


    return meets_criteria


with open(os.path.abspath(os.path.dirname(__file__))+'/../config/tickers.txt', 'r') as file:
	tickers = [line.strip() for line in file if line.strip()]
for ticker in tickers:
    print (f"Checking {ticker}...")
    if check_stock_criteria(ticker):
        print(f"{ticker} meets the criteria.")
    else:
        print(f"{ticker} does not meet the criteria.")
    print("\n\n")
