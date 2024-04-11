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
        self.position = copy.deepcopy({'STARFRUIT': 0, 'AMETHYSTS': 0})
        self.star_cache = []
        self.star_poly_order = 8
        self.SMOOTHING = 0.98

        self.am_window_size = 34
        self.am_position_open = False
        self.am_position_type = None
        self.am_historical_bid_prices = []
        self.am_historical_ask_prices = []
        self.am_remaining_quantity = 0
        self.am_open_order_volume = 0
        self.am_partially_closed = False
        self.am_latest_price = 0
    
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

        # undercut_buy = best_buy + 1
        # undercut_sell = best_sell - 1

        # bid_price = min(undercut_buy, acc_bid)
        # ask_price = max(undercut_sell, acc_ask)
        
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

            self.am_window_size = saved_state.am_window_size
            self.am_position_open = saved_state.am_position_open
            self.am_position_type = saved_state.am_position_type
            self.am_historical_bid_prices = saved_state.am_historical_bid_prices
            self.am_historical_ask_prices = saved_state.am_historical_ask_prices
            self.am_remaining_quantity = saved_state.am_remaining_quantity
            self.am_open_order_volume = saved_state.am_open_order_volume
            self.am_partially_closed = saved_state.am_partially_closed
            self.am_latest_price = saved_state.am_latest_price

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

        star = True
        # Use predicted next price to determine acceptable bids and asks
        if len(self.star_cache) == self.star_poly_order:
            star_band_lower = self.calc_next_price() - 1
            star_band_upper = self.calc_next_price() + 1

        else:
            print("Not enough data")
            star = False

        star_orders = self.create_orders_regression('STARFRUIT', state.order_depths['STARFRUIT'], star_band_lower, star_band_upper, 20) if star else []
        
        result['STARFRUIT'] = star_orders

        if 'AMETHYSTS' in state.order_depths:
            am_order_depth = state.order_depths['AMETHYSTS']
            am_orders = []

            if am_order_depth.buy_orders and am_order_depth.sell_orders:
                am_bid_price = max(am_order_depth.buy_orders)
                self.am_historical_bid_prices.append(am_bid_price)

            if len(self.am_historical_bid_prices) > 20:

                am_live_ask_price, am_live_ask_volume = list(am_order_depth.sell_orders.items())[0]
                am_live_bid_price, am_live_bid_volume = list(am_order_depth.buy_orders.items())[0]

                if not self.am_position_open:
                    if am_live_bid_price > 10000:
                        self.am_open_order_volume = min(abs(am_live_bid_volume)+3, 20)
                        am_orders.append(Order('AMETHYSTS', am_live_bid_price-1, -self.am_open_order_volume))
                        self.am_latest_price = am_live_bid_price
                        self.am_position_open = True
                        self.am_position_type = 'Short'
                        self.am_remaining_quantity = self.am_open_order_volume
                    elif am_live_ask_price < 10000:
                        self.am_open_order_volume = min(abs(am_live_ask_volume)+3, 20)
                        am_orders.append(Order('AMETHYSTS', am_live_ask_price+1, self.am_open_order_volume))
                        self.am_latest_price = am_live_ask_price
                        self.am_position_open = True
                        self.am_position_type = 'Long'
                        self.am_remaining_quantity = self.am_open_order_volume
                        
                elif self.am_position_open:
                    if not self.am_partially_closed:
                        if self.am_position_type == 'Long' and am_live_ask_price < 10000:
                            am_additional_volume = min(abs(20-self.am_remaining_quantity), abs(am_live_ask_volume))
                            am_orders.append(Order('AMETHYSTS', am_live_ask_price, am_additional_volume))
                            self.am_remaining_quantity += am_additional_volume
                            self.am_position_open = True
                            self.am_position_type = 'Long'
                        elif self.am_position_type == 'Short' and am_live_bid_price > 10000:
                            am_additional_volume = min(abs(20-self.am_remaining_quantity), abs(am_live_bid_volume))
                            am_orders.append(Order('AMETHYSTS', am_live_bid_price, -am_additional_volume))
                            self.am_remaining_quantity += am_additional_volume
                            self.am_position_open = True
                            self.am_position_type = 'Short'
                        if self.am_position_type == 'Short' and (am_live_ask_price < 10000 or am_live_ask_price < self.am_latest_price):
                            am_closing_volume = min(abs(am_live_ask_volume)+3, 20+self.am_remaining_quantity)
                            am_orders.append(Order('AMETHYSTS', am_live_ask_price+1, am_closing_volume))
                            if self.am_remaining_quantity > am_closing_volume:
                                self.am_partially_closed = True
                                self.am_position_open = True
                                self.am_position_type = 'Short'
                                self.am_remaining_quantity -= am_closing_volume
                            elif self.am_remaining_quantity == am_closing_volume:
                                self.am_position_open = False
                                self.am_partially_closed = False
                                self.am_remaining_quantity -= am_closing_volume
                            elif self.am_remaining_quantity < am_closing_volume:
                                self.am_latest_price = am_live_ask_price
                                self.am_position_open = True
                                self.am_partially_closed = False
                                self.am_position_type = 'Long'
                                self.am_remaining_quantity = (am_closing_volume - self.am_remaining_quantity)
                                
                        elif self.am_position_type == 'Long' and (am_live_bid_price > 10000 or am_live_bid_price > self.am_latest_price):
                            am_closing_volume = min(abs(am_live_bid_volume)+3, 20+self.am_remaining_quantity)
                            am_orders.append(Order('AMETHYSTS', am_live_bid_price-1, -am_closing_volume))
                            if self.am_remaining_quantity > am_closing_volume:
                                self.am_partially_closed = True
                                self.am_position_open = True
                                self.am_position_type = 'Long'
                                self.am_remaining_quantity -= am_closing_volume
                            elif self.am_remaining_quantity == am_closing_volume:
                                self.am_partially_closed = False
                                self.am_position_open = False
                                self.am_remaining_quantity -= am_closing_volume
                            elif self.am_remaining_quantity < am_closing_volume:
                                self.am_latest_price = am_live_bid_price
                                self.am_position_open = True
                                self.am_partially_closed = False
                                self.am_position_type = 'Short'
                                self.am_remaining_quantity = (am_closing_volume - self.am_remaining_quantity)
                                
                    elif self.am_partially_closed:
                        if self.am_position_type == 'Long' and am_live_ask_price < 10000:
                            am_additional_volume = min(abs(20-self.am_remaining_quantity), abs(am_live_ask_volume))
                            am_orders.append(Order('AMETHYSTS', am_live_ask_price, am_additional_volume))
                            self.am_remaining_quantity += am_additional_volume
                            self.am_position_open = True
                            self.am_position_type = 'Long'
                        elif self.am_position_type == 'Short' and am_live_bid_price > 10000:
                            am_additional_volume = min(abs(20-self.am_remaining_quantity), abs(am_live_bid_volume))
                            am_orders.append(Order('AMETHYSTS', am_live_bid_price, -am_additional_volume))
                            self.am_remaining_quantity += am_additional_volume
                            self.am_position_open = True
                            self.am_position_type = 'Short'
                        if self.am_position_type == 'Short' and (am_live_ask_price < 10000 or am_live_ask_price < self.am_latest_price):
                            am_order_quantity = min(abs(am_live_ask_volume)+3, 20+self.am_remaining_quantity)
                            am_orders.append(Order('AMETHYSTS', am_live_ask_price+1, am_order_quantity))
                            if self.am_remaining_quantity > am_order_quantity:
                                self.am_partially_closed = True
                                self.am_position_open = True
                                self.am_position_type = 'Short'
                                self.am_remaining_quantity -= am_order_quantity
                            elif self.am_remaining_quantity == am_order_quantity:
                                self.am_position_open = False
                                self.am_partially_closed = False
                                self.am_remaining_quantity -= am_order_quantity
                            elif self.am_remaining_quantity < am_order_quantity:
                                self.am_latest_price = am_live_ask_price
                                self.am_position_open = True
                                self.am_partially_closed = False
                                self.am_position_type = 'Long'
                                self.am_remaining_quantity = (am_order_quantity - self.am_remaining_quantity)
                        elif self.am_position_type == 'Long' and (am_live_bid_price > 10000 or am_live_bid_price > self.am_latest_price):
                            am_order_quantity = min(abs(am_live_bid_volume)+3, 20+self.am_remaining_quantity)
                            am_orders.append(Order('AMETHYSTS', am_live_bid_price-1, -am_order_quantity))
                            if self.am_remaining_quantity > am_order_quantity:
                                self.am_partially_closed = True
                                self.am_position_open = True
                                self.am_position_type = 'Long'
                                self.am_remaining_quantity -= am_order_quantity
                            elif self.am_remaining_quantity == am_order_quantity:
                                self.am_partially_closed = False
                                self.am_position_open = False
                                self.am_remaining_quantity -= am_order_quantity
                            elif self.am_remaining_quantity < am_order_quantity:
                                self.am_latest_price = am_live_bid_price
                                self.am_position_open = True
                                self.am_partially_closed = False
                                self.am_position_type = 'Short'
                                self.am_remaining_quantity = (am_order_quantity - self.am_remaining_quantity)
            

            result['AMETHYSTS'] = am_orders
            
            return result, conversions, jsonpickle.encode(self)
