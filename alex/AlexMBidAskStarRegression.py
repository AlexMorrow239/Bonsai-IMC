from typing import List
from datamodel import OrderDepth, TradingState, Order
import collections
from collections import defaultdict
import copy
import numpy as np
import jsonpickle

# Author: Rick Howell, Alex Morrow
# University of Miami, 2024

class Trader:
    def __init__ (self):
        self.position = copy.deepcopy({'STARFRUIT': 0, 'AMETHYSTS': 0})
        self.star_window_size = 10
        self.SMOOTHING = 0.9
        self.cpnl = defaultdict(lambda: 0)
        self.star_cache_bid = []
        self.star_cache_ask = []
    
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

        smoothed_star_cache_bid = self.filter(self.star_cache_bid)
        a,b,c,d,intercept = np.polyfit(range(0, len(smoothed_star_cache_bid)), smoothed_star_cache_bid, 4)
        t = len(self.star_cache_bid) + self.star_window_size/4
        next_price_bid = (a * t**4) + (b * t**3) + (c * t**2) + (d * t) + intercept

        smoothed_star_cache_ask = self.filter(self.star_cache_ask)
        a,b,c,d,intercept = np.polyfit(range(0, len(smoothed_star_cache_ask)), smoothed_star_cache_ask, 4)
        t = len(self.star_cache_ask) + self.star_window_size/4
        next_price_ask = (a * t**4) + (b * t**3) + (c * t**2) + (d * t) + intercept
        
        return int(round(next_price_bid)), int(round(next_price_ask))
    
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
            self.star_window_size = saved_state.star_window_size
            self.SMOOTHING = saved_state.SMOOTHING
            self.cpnl = saved_state.cpnl
        
        self.position['STARFRUIT'] = state.position.get('STARFRUIT', 0) # Update position
        print(f"OFFICIAL POSITION: {self.position['STARFRUIT']}")

        # Ensure coefficients do not exceed window_size, remove oldest bid and ask if it does
        if len(self.star_cache_ask) == self.star_window_size:
            self.star_cache_bid.pop(0)
            self.star_cache_ask.pop(0)

        # Get the best buy and sell prices
        star_best_sell = min(state.order_depths['STARFRUIT'].sell_orders.keys())
        star_best_buy = max(state.order_depths['STARFRUIT'].buy_orders.keys())

        # Update the caches with the new ask and bid prices
        self.star_cache_bid.append(star_best_buy)
        self.star_cache_ask.append(star_best_sell)


        star_band_lower = INF
        star_band_upper = INF

        # Use predicted next price to determine acceptable bids and asks
        if len(self.star_cache_ask) == self.star_window_size:
            star_band_lower, star_band_upper = self.calc_next_price()
            star_band_lower += 1
            star_band_upper -= 1
            print(f"STARFRUIT BAND: {star_band_lower} - {star_band_upper}")
        else:
            print("Not enough data")
            return result, conversions, jsonpickle.encode(self)

        star_orders = self.create_orders_regression('STARFRUIT', state.order_depths['STARFRUIT'], star_band_lower, star_band_upper, 20)
        
        result['STARFRUIT'] = star_orders
        print(f"STARFRUIT: {star_orders}")

        if False:
            for product in state.own_trades.keys():
                for trade in state.own_trades[product]:

                    if trade.timestamp != (state.timestamp-100):
                        continue

                    if product == 'STARFRUIT':
                        print(f"TRADE: buyer={trade.buyer}, seller={trade.seller}price={trade.price}, quantity={trade.quantity}, timestamp={trade.timestamp}")
                        print(f"PREVIOUS PNL: {self.cpnl['STARFRUIT']}")
                
                    if trade.buyer == 'SUBMISSION':
                        self.cpnl[product] -= (trade.price * trade.quantity)
                        print(f"BUYING {trade.quantity} {product} at {trade.price} for {trade.price * trade.quantity}")
                    else:
                        self.cpnl[product] += (trade.price * trade.quantity)
                        print(f"SELLING {trade.quantity} {product} at {trade.price} for {trade.price * trade.quantity}")
                    print(f"CUMULATIVE PNL AFTER: {self.cpnl['STARFRUIT']}")
            
            print(f"CUMULATIVE PNL: {self.cpnl['STARFRUIT']}")

        return result, conversions, jsonpickle.encode(self)


        
                                        
        
        


        
                                        
        
        