from typing import Dict, List
from datamodel import OrderDepth, TradingState, Order
import collections
from collections import defaultdict
import random
import math
import copy
import numpy as np
import jsonpickle

# Author: Rick Howell, Alex Morrow
# University of Miami, 2024

class Trader:
    def __init__ (self):
        self.position = copy.deepcopy({'STARFRUIT': 0, 'AMETHYSTS': 0})
        self.star_cache = []
        self.star_poly_order = 8
        self.SMOOTHING = 0.98
    
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
        

    def calc_next_price(self):

        smoothed_star_cache = self.filter(self.star_cache)
        a,b,c,d,intercept = np.polyfit(range(0, len(smoothed_star_cache)), smoothed_star_cache, 4)
        
        t = len(self.star_cache) + self.star_poly_order/4
        next_price = (a * t**4) + (b * t**3) + (c * t**2) + (d * t) + intercept
        
        return int(round(next_price))
    
    def create_orders_regression(self, product, order_depth, acc_bid, acc_ask, LIMIT):
        orders: list[Order] = []

        osell = collections.OrderedDict(sorted(order_depth.sell_orders.items()))
        obuy = collections.OrderedDict(sorted(order_depth.buy_orders.items(), reverse=True))

        cur_position = prior_position = self.position['STARFRUIT']

        cum_buy_quant = prior_position
        for ask, vol in osell.items():
            if((ask <= acc_bid) or ((self.position[product] < 0) and (ask == acc_bid + 1))) and cur_position < LIMIT:
                quantity = min(abs(vol), (LIMIT - cur_position), (LIMIT - cum_buy_quant))
                cur_position += quantity
                cum_buy_quant += quantity
                assert(quantity >= 0)
                orders.append(Order(product, ask, quantity)) if cum_buy_quant <= 20 else None
        
        cum_sell_quant = prior_position
        for bid, vol in obuy.items():
            if((bid >= acc_ask) or ((self.position[product] > 0) and ((bid + 1) == acc_ask))) and cur_position > -LIMIT:
                quantity = max(-vol, (-LIMIT - cur_position), (-LIMIT - cum_sell_quant))
                cur_position += quantity
                cum_sell_quant += quantity
                assert(quantity <= 0)
                orders.append(Order(product, bid, quantity)) if cum_sell_quant >= -20 else None
        
        self.position['STARFRUIT'] = cur_position
        
        return orders

    def run(self, state: TradingState):
        INF = int(1e9)
        conversions = 1
        result = {}

        if state.traderData:
            saved_state = jsonpickle.decode(state.traderData)
            self.position = saved_state.position
            self.star_cache = saved_state.star_cache
            self.star_poly_order = saved_state.star_poly_order
            self.SMOOTHING = saved_state.SMOOTHING
        
        self.position['STARFRUIT'] = state.position.get('STARFRUIT', 0) # Update position
        print(f"OFFICIAL POSITION: {self.position['STARFRUIT']}")

        # Ensure coefficients do not exceed 12, remove oldest mid_price if it does
        if len(self.star_cache) == self.star_poly_order:
            removed = self.star_cache.pop(0)

        # Get the best buy and sell prices
        star_best_sell = min(state.order_depths['STARFRUIT'].sell_orders.keys())
        star_best_buy = max(state.order_depths['STARFRUIT'].buy_orders.keys())

        # Update the cache with the new mid_price
        self.star_cache.append((star_best_sell + star_best_buy) / 2)


        star_band_lower = INF
        star_band_upper = INF

        # Use predicted next price to determine acceptable bids and asks
        if len(self.star_cache) == self.star_poly_order:
            star_band_lower = self.calc_next_price() - 1
            star_band_upper = self.calc_next_price() + 1
            print(f"STARFRUIT BAND: {star_band_lower} - {star_band_upper}")

        else:
            print("Not enough data")
            return result, conversions, jsonpickle.encode(self)

        star_orders = self.create_orders_regression('STARFRUIT', state.order_depths['STARFRUIT'], star_band_lower, star_band_upper, 19)
        
        result['STARFRUIT'] = star_orders
        print(f"STARFRUIT: {star_orders}")

        return result, conversions, jsonpickle.encode(self)
