import pandas as pd
import numpy as np
import talib as ta
import os

# set variables from environment
RSI_timeperiod = int(os.environ.get("RSI_timeperiod",14))
SMA_timeperiod = int(os.environ.get("SMA_timeperiod",200))
LINEARREG_timeperiod = int(os.environ.get("LINEARREG_timeperiod",10))

def rsi(df,timeperiod=14,label="RSI",):
    df[label] = ta.RSI(df['Close'].to_numpy(), timeperiod=timeperiod)
    return df

def sma(df,timeperiod=200,label="SMA"):
    df[label] = ta.SMA(df['Close'], timeperiod=timeperiod)
    return df 

def linearreg(df,timeperiod=10):
    df['LINEARREG'] = ta.LINEARREG(df['Close'].to_numpy(), timeperiod=timeperiod) # b+m*(period-1)
    df['LINEARREG_SLOPE'] = ta.LINEARREG_SLOPE(df['Close'].to_numpy(), timeperiod=timeperiod) # m
    df['LINEARREG_INTERCEPT'] = ta.LINEARREG_INTERCEPT(df['Close'].to_numpy(), timeperiod=timeperiod) # b
    df['LRFORECAST'] = df['LINEARREG_INTERCEPT'].to_numpy() + df['LINEARREG_SLOPE'].to_numpy() * timeperiod
    return df

def macd(df,fastperiod=12,slowperiod=26,signalperiod=9):
	macd, macdsignal, macdhist = ta.MACD(df['Close'].to_numpy(), fastperiod=fastperiod, slowperiod=slowperiod, signalperiod=signalperiod)
	df['MACD'] = macd
	df['MACD_SIGNAL'] = macdsignal
	df['MACD_HIST'] = macdhist
	return df

def bb(df,timeperiod=20,nbdevup=2,nbdevdn=2,matype=0):
	upperband, middleband, lowerband = ta.BBANDS(df['Close'].to_numpy(), timeperiod=timeperiod, nbdevup=nbdevup, nbdevdn=nbdevdn, matype=matype)
	df['BB_UPPER'] = upperband
	df['BB_MIDDLE'] = middleband
	df['BB_LOWER'] = lowerband
	return df
