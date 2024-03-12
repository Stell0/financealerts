import os

RSI_upper = int(os.environ.get("RSI_upper",70))
RSI_lower = int(os.environ.get("RSI_lower",30))
RSI_upper2 = int(os.environ.get("RSI_upper2",80))
RSI_lower2 = int(os.environ.get("RSI_lower2",20))

def rsi(df):
    # add 1 to signal column if RSI is under RSI_lower2
    df.loc[df['RSI'] < RSI_lower2, 'signal'] += 1
    df.loc[df['RSI'] < RSI_lower2, 'reason'] += "RSI is under RSI_lower2,"
               
    # add 1 to signal column if RSI is under RSI_lower
    df.loc[df['RSI'] < RSI_lower, 'signal'] += 1
    df.loc[df['RSI'] < RSI_lower, 'reason'] += "RSI is under RSI_lower,"

    # remove 1 from signal column if RSI is over RSI_upper2
    df.loc[df['RSI'] > RSI_upper2, 'signal'] -= 1
    df.loc[df['RSI'] > RSI_upper2, 'reason'] += "RSI is over RSI_upper2,"

    # remove 1 from signal column if RSI is over RSI_upper
    df.loc[df['RSI'] > RSI_upper, 'signal'] -= 1
    df.loc[df['RSI'] > RSI_upper, 'reason'] += "RSI is over RSI_upper,"
    return df

def sma(df,label="SMA"):
    # add 1 to signal column if price is approaching SMA from above
    df.loc[(df['Close'] > df[label]) & (df['LRFORECAST'] < df[label]), 'signal'] += 1
    df.loc[(df['Close'] > df[label]) & (df['LRFORECAST'] < df[label]), 'reason'] += "price is approaching SMA from above,"

    # remove 1 from signal column if price is approaching SMA from below
    df.loc[(df['Close'] < df[label]) & (df['LRFORECAST'] > df[label]), 'signal'] -= 1
    df.loc[(df['Close'] < df[label]) & (df['LRFORECAST'] > df[label]), 'reason'] += "price is approaching SMA from below,"
    return df

def movingAverageCrossover(df,short='SMA40',long='SMA'):
	# add 1 to signal column if short MA is approaching long MA from above
	df.loc[(df[short] > df[long]) & (df[short].shift(1) < df[long].shift(1)), 'signal'] += 1
	df.loc[(df[short] > df[long]) & (df[short].shift(1) < df[long].shift(1)), 'reason'] += f"{short} MA is approaching {long} MA from above,"

	# remove 1 from signal column if short MA is approaching long MA from below
	df.loc[(df[short] < df[long]) & (df[short].shift(1) > df[long].shift(1)), 'signal'] -= 1
	df.loc[(df[short] < df[long]) & (df[short].shift(1) > df[long].shift(1)), 'reason'] += f"{short} MA is approaching {long} MA from below,"
	return df

def macd(df):
     # add 1 to signal when the MACD line crosses above the signal line.
	df.loc[(df['MACD'] > df['MACD_SIGNAL']) & (df['MACD'].shift(1) < df['MACD_SIGNAL'].shift(1)), 'signal'] += 1
	df.loc[(df['MACD'] > df['MACD_SIGNAL']) & (df['MACD'].shift(1) < df['MACD_SIGNAL'].shift(1)), 'reason'] += "MACD line crosses above the signal line,"
      
	 # remove 1 from signal when the MACD line crosses below the signal line.
	df.loc[(df['MACD'] < df['MACD_SIGNAL']) & (df['MACD'].shift(1) > df['MACD_SIGNAL'].shift(1)), 'signal'] -= 1
	df.loc[(df['MACD'] < df['MACD_SIGNAL']) & (df['MACD'].shift(1) > df['MACD_SIGNAL'].shift(1)), 'reason'] += "MACD line crosses below the signal line,"
	return df

def bb(df):
    #add 1 to signal when the price crosses below the lower Bollinger Band
	df.loc[(df['Close'] < df['BB_LOWER']) & (df['Close'].shift(1) > df['BB_LOWER'].shift(1)), 'signal'] += 1
	df.loc[(df['Close'] < df['BB_LOWER']) & (df['Close'].shift(1) > df['BB_LOWER'].shift(1)), 'reason'] += "price crosses below the lower Bollinger Band,"

	#remove 1 from signal when the price crosses above the upper Bollinger Band
	df.loc[(df['Close'] > df['BB_UPPER']) & (df['Close'].shift(1) < df['BB_UPPER'].shift(1)), 'signal'] -= 1
	df.loc[(df['Close'] > df['BB_UPPER']) & (df['Close'].shift(1) < df['BB_UPPER'].shift(1)), 'reason'] += "price crosses above the upper Bollinger Band,"
	return df


