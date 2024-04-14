from typing import Dict, List
from datamodel import OrderDepth, TradingState, Order
import collections
from collections import defaultdict
import random
import math
import copy
import numpy as np
import jsonpickle

class Trader:
    
    def __init__(self):
        # Global
        self.position = {'STARFRUIT': 0, 'AMETHYSTS': 0}
        # STARFRUIT
        self.star_cache = []
        self.star_window_size = 8
        # AMETHYSTS
        self.am_remaining_quantity = 0
        self.am_partially_closed = False
        self.am_latest_price = 0

    def run(self, state: TradingState):
        INF = int(1e9)
        conversions = 1
        result = {}

        if state.traderData:
            saved_state = jsonpickle.decode(state.traderData)
            #Global
            self.position = saved_state.position
            # STARFRUIT
            self.star_cache = saved_state.star_cache
            self.star_window_size = saved_state.star_window_size
            # AMETHYSTS
            self.am_remaining_quantity = saved_state.am_remaining_quantity
            self.am_partially_closed = saved_state.am_partially_closed
            self.am_latest_price = saved_state.am_latest_price

        # Update positions for each procuct
        for product in state.order_depths:
            self.position[product] = state.position.get(product, 0) # Update position

        # STARFRUIT
        # Ensure STARFRUIT coefficients do not exceed 12, remove oldest mid_price if it does
        if len(self.star_cache) == self.star_window_size:
            self.star_cache.pop(0)
        # Get the best buy and sell prices for STARFRUIT
        star_best_sell, star_best_buy = self.get_best_prices(state.order_depths['STARFRUIT'])
        self.star_cache.append((star_best_sell + star_best_buy) / 2)    # Append the mid price to the cache

        star_band_lower = INF
        star_band_upper = INF
        star = True
        
        if len(self.star_cache) == self.star_window_size:
            # Use predicted next price to determine acceptable bids and asks
            star_band_lower = self.calc_next_price_regression() - 1.0
            star_band_upper = self.calc_next_price_regression() + 1.0
            star_orders = self.create_orders_regression('STARFRUIT', state.order_depths['STARFRUIT'], star_band_lower, star_band_upper, 19)
        else:
            print("Not enough data")
            star_orders = []
        result['STARFRUIT'] = star_orders

        # AMETHYSTS
        if state.timestamp > 2000:
            am_order_depth = state.order_depths['AMETHYSTS']
            am_orders = []
            am_orders = self.create_orders_amethysts(am_order_depth)
        else:
            am_orders = []
        result['AMETHYSTS'] = am_orders

        return result, conversions, jsonpickle.encode(self)
    
    # Returns best_ask, best_bid
    # Or best ask, best ask volume, best bid, best bid volume
    def get_best_prices(self, order_depth: OrderDepth, volumes = False):
        if volumes:
            best_ask, best_ask_volume = list(order_depth.sell_orders.items())[0]
            best_bid, best_bid_volume = list(order_depth.buy_orders.items())[0]
            return best_ask, best_ask_volume, best_bid, best_bid_volume
        else:
            return min(order_depth.sell_orders.keys()), max(order_depth.buy_orders.keys())
    
    def smooth_data(self, z: List, SMOOTHING) -> List:
            z_doubled = z

            z_fft = np.fft.fft(z_doubled)
            n = len(z_doubled)
            filter = []
            for i in range(n):
                if i < (n / 2) *  (1 - SMOOTHING) or i > (n / 2) * (1 + SMOOTHING):
                    filter.append(1)
                else:
                    filter.append(0)
            z_smoothed = np.fft.ifft(z_fft * filter)
            z1 = list(z_smoothed.flatten())
            return z1
        

    def calc_next_price_regression(self):

        SMOOTHING = 0.99
        smoothed_star_cache = self.smooth_data(self.star_cache, SMOOTHING)
        a,b,c,d,intercept = np.polyfit(range(0, len(smoothed_star_cache)), smoothed_star_cache, 4)
        
        t = len(self.star_cache) + self.star_window_size/4
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
        
        self.position[product] = cur_position
        
        return orders
    
    def open_order_high_frequency(self, best_bid, best_ask, best_bid_volume, best_ask_volume):
        orders = []
        if best_bid > 10000:
            am_open_order_volume = min(abs(best_bid_volume)+3, 20)
            orders.append(Order('AMETHYSTS', best_bid-1, -am_open_order_volume))
            self.am_latest_price = best_bid
            self.am_remaining_quantity = am_open_order_volume
        elif best_ask < 10000:
            am_open_order_volume = min(abs(best_ask_volume)+3, 20)
            orders.append(Order('AMETHYSTS', best_ask+1, am_open_order_volume))
            self.am_latest_price = best_ask
            self.am_remaining_quantity = am_open_order_volume
        return orders
    
    def handle_not_partially_closed_high_frequency(self, product, current_position, ask_price, bid_price, ask_volume, bid_volume):

        orders = []
        if current_position > 0 and ask_price < 10000:
            additional_volume = min(abs(20-self.am_remaining_quantity), abs(ask_volume)+3)
            orders.append(Order(product, ask_price+1, additional_volume))
            self.am_remaining_quantity += additional_volume
        elif current_position < 0 and bid_price > 10000:
            additional_volume = min(abs(20-self.am_remaining_quantity), abs(bid_volume)+3)
            orders.append(Order(product, bid_price-1, -additional_volume))
            self.am_remaining_quantity += additional_volume
        if current_position < 0 and (ask_price < 10000 or ask_price < self.am_latest_price):
            am_closing_volume = min(abs(ask_volume)+3, 20+self.am_remaining_quantity)
            orders.append(Order(product, ask_price+1, am_closing_volume))
            if self.am_remaining_quantity > am_closing_volume:
                self.am_partially_closed = True
                self.am_remaining_quantity -= am_closing_volume
            elif self.am_remaining_quantity == am_closing_volume:
                self.am_partially_closed = False
                self.am_remaining_quantity -= am_closing_volume
            elif self.am_remaining_quantity < am_closing_volume:
                self.am_latest_price = ask_price
                self.am_partially_closed = False
                self.am_remaining_quantity = (am_closing_volume - self.am_remaining_quantity)
                
        elif current_position > 0 and (bid_price > 10000 or bid_price > self.am_latest_price):
            am_closing_volume = min(abs(bid_volume)+3, 20+self.am_remaining_quantity)
            orders.append(Order(product, bid_price-1, -am_closing_volume))
            if self.am_remaining_quantity > am_closing_volume:
                self.am_partially_closed = True
                self.am_remaining_quantity -= am_closing_volume
            elif self.am_remaining_quantity == am_closing_volume:
                self.am_partially_closed = False
                self.am_remaining_quantity -= am_closing_volume
            elif self.am_remaining_quantity < am_closing_volume:
                self.am_latest_price = bid_price
                self.am_partially_closed = False
                self.am_remaining_quantity = (am_closing_volume - self.am_remaining_quantity)

        return orders
    
    def handle_partially_closed_high_frequency(self, product, current_position, ask_price, bid_price, ask_volume, bid_volume):
        orders = []
        if current_position > 0 and ask_price < 10000:
            am_additional_volume = min(abs(20-self.am_remaining_quantity), abs(ask_volume)+3)
            orders.append(Order(product, ask_price+1, am_additional_volume))
            self.am_remaining_quantity += am_additional_volume
        elif current_position < 0 and bid_price > 10000:
            am_additional_volume = min(abs(20-self.am_remaining_quantity), abs(bid_volume)+3)
            orders.append(Order(product, bid_price-1, -am_additional_volume))
            self.am_remaining_quantity += am_additional_volume
        if current_position < 0 and (ask_price < 10000 or ask_price < self.am_latest_price):
            am_order_quantity = min(abs(ask_volume)+3, 20+self.am_remaining_quantity)
            orders.append(Order(product, ask_price+1, am_order_quantity))
            if self.am_remaining_quantity > am_order_quantity:
                self.am_partially_closed = True
                self.am_remaining_quantity -= am_order_quantity
            elif self.am_remaining_quantity == am_order_quantity:
                self.am_partially_closed = False
                self.am_remaining_quantity -= am_order_quantity
            elif self.am_remaining_quantity < am_order_quantity:
                self.am_latest_price = ask_price
                self.am_partially_closed = False
                self.am_remaining_quantity = (am_order_quantity - self.am_remaining_quantity)
        elif current_position > 0 and (bid_price > 10000 or bid_price > self.am_latest_price):
            am_order_quantity = min(abs(bid_volume)+3, 20+self.am_remaining_quantity)
            orders.append(Order(product, bid_price-1, -am_order_quantity))
            if self.am_remaining_quantity > am_order_quantity:
                self.am_partially_closed = True
                self.am_remaining_quantity -= am_order_quantity
            elif self.am_remaining_quantity == am_order_quantity:
                self.am_partially_closed = False
                self.am_remaining_quantity -= am_order_quantity
            elif self.am_remaining_quantity < am_order_quantity:
                self.am_latest_price = bid_price
                self.am_partially_closed = False
                self.am_remaining_quantity = (am_order_quantity - self.am_remaining_quantity)
        return orders
    
    def create_orders_amethysts(self, am_order_depth):
        am_live_ask_price, am_live_ask_volume, am_live_bid_price, am_live_bid_volume = self.get_best_prices(am_order_depth, volumes=True)
        am_orders = []
        am_cur_position = self.position['AMETHYSTS']

        if am_cur_position == 0:
            am_orders = self.open_order_high_frequency(am_live_bid_price, am_live_ask_price, am_live_bid_volume, am_live_ask_volume)
        elif am_cur_position != 0 and not self.am_partially_closed:
            am_orders = self.handle_not_partially_closed_high_frequency('AMETHYSTS', am_cur_position, am_live_ask_price, am_live_bid_price, am_live_ask_volume, am_live_bid_volume)
                        
        elif am_cur_position != 0 and self.am_partially_closed:
            am_orders = self.handle_partially_closed_high_frequency('AMETHYSTS', am_cur_position, am_live_ask_price, am_live_bid_price, am_live_ask_volume, am_live_bid_volume)
        return am_orders

    

