from datamodel import OrderDepth, UserId, TradingState, Order
from typing import List
import string
import pandas as pd
import numpy as np
import jsonpickle

class Trader:
    # Constants
    # SMOOTHING: factor for the filter [0, 1)
    # NBHD: Number of points to consider for the regression
    # K: Threshold for the residual
    # TIMESTAMP_DELTA: Time interval for each step

    SMOOTHING       = 0.7
    NBHD            = 32
    K               = 0.1
    TIMESTAMP_DELTA = 100

    def __init__(self):
        self.prices_history = {}
        self.position_open = {}
        self.position_type = {}

        self.window = []

    def window_append(self, x):
        if len(self.window) > self.NBHD:
            self.window.pop(0)
        self.window.append(x)

    def window_append_list(self, x: List):
        for i in x:
            self.window_append(i)

    def window_clear(self):
        self.window = []

    def residual(self, pred, actual) -> float:
        return actual - pred
    
    # takes a list with (usually) timestamp and price columns
    # returns [a, b] from the regression equation y = ax + b
    def regression(self, z: List) -> tuple[float, float]:
        n = len(z)
        x = []
        for i in range(n):
            x.append(i)
        y = np.array(z)
        a, b = np.polyfit(x, y, 1)
        return a, b
    
    # takes a list and returns a smoothed list of the same size
    def filter(self, z: List) -> List:
        z_doubled = z

        z_fft = np.fft.fft(z_doubled)
        n = len(z_doubled)
        filter = []
        for i in range(n):
            if i < (n / 2) *  (1 - self.SMOOTHING) or i > (n / 2) * (1 + self.SMOOTHING):
                filter.append(1)
            else:
                filter.append(0)
        z_smoothed = np.fft.ifft(z_fft * filter)
        z1 = list(z_smoothed.flatten())
        return z1

    def run(self, state: TradingState):
        print("traderData: " + state.traderData)
        print("Observations: " + str(state.observations))

        # Deserialize traderData to get the trader state
        if state.traderData:
            savedState = jsonpickle.decode(state.traderData)
            self.prices_history = savedState.prices_history
            self.position_open = savedState.position_open
            self.position_type = savedState.position_type

				# Orders to be placed on exchange matching engine
        result = {}
        for product in state.order_depths:
            order_depth: OrderDepth = state.order_depths[product]
            orders: List[Order] = []
            best_ask, best_ask_amount = list(order_depth.sell_orders.items())[0]
            best_bid, best_bid_amount = list(order_depth.buy_orders.items())[0]

            self.window_append(best_ask)
            if len(self.window) > self.NBHD:
                win_smoothed = self.filter(self.window)
                a, b = self.regression(win_smoothed)
                residual = self.residual(best_ask, a * len(self.window) + b)
            else:
                residual = 0

            if (len(order_depth.sell_orders) != 0) and state.timestamp / self.TIMESTAMP_DELTA > self.NBHD:
                
                if residual < self.K:
                    print("BUY", str(-best_ask_amount) + "x", best_ask)
                    orders.append(Order(product, best_ask, -best_ask_amount))
    
            if len(order_depth.buy_orders) != 0:
                if residual > -self.K:
                    print("SELL", str(best_bid_amount) + "x", best_bid)
                    orders.append(Order(product, best_bid, -best_bid_amount))
            
            result[product] = orders
    
		    # String value holding Trader state data required. 
				# It will be delivered as TradingState.traderData on next execution.
        traderData = jsonpickle.encode(self)
        
				# Sample conversion request. Check more details below. 
        conversions = 1
        return result, conversions, traderData