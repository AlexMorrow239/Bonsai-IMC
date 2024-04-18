from typing import Dict, List, Union, Any, Tuple
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
        self.position = {'STARFRUIT': 0, 'AMETHYSTS': 0, 'ORCHIDS': 0, 'CHOCOLATE': 0, 'STRAWBERRIES': 0, 'ROSES': 0, 'GIFT_BASKET': 0}
        # BASKET
        self.position_limits = {'STARFRUIT': 20, 'AMETHYSTS': 20, 'ORCHIDS': 100, 'CHOCOLATE': 250, 'STRAWBERRIES': 350, 'ROSES': 60, 'GIFT_BASKET': 60}
        self.window_sizes = {'STARFRUIT': 10, 'CHOCOLATE': 10, 'STRAWBERRIES': 10, 'ROSES': 10}
        self.caches = {'STARFRUIT': [], 'CHOCOLATE': [], 'STRAWBERRIES': [], 'ROSES': []}
        self.SMOOTHING = {'STARFRUIT': 0.99, 'CHOCOLATE': 0.99, 'STRAWBERRIES': 0.99, 'ROSES': 0.99}


    def get_best_prices(self, order_depth: OrderDepth) -> Tuple[int, int, int, int]:
        if order_depth.buy_orders:
            best_bid = max(order_depth.buy_orders.keys(), default=0)
            best_bid_volume = order_depth.buy_orders.get(best_bid, 0)
        else:
            best_bid = 0
            best_bid_volume = 0
        if order_depth.sell_orders:
            best_ask = min(order_depth.sell_orders.keys(), default=float('inf'))
            best_ask_volume = order_depth.sell_orders.get(best_ask, 0)
        else:
            best_ask = float('inf')
            best_ask_volume = 0

        return best_bid, best_bid_volume, best_ask, best_ask_volume

    def place_order(self, product: str, price: Dict[str, Dict[str, int]], quantity: int) -> List[Order]:
        order = None
        current_position = self.position[product]
        LIMIT = self.position_limits[product]
        if quantity > 0:  # Buying
            available_capacity = LIMIT - current_position
            quantity_to_order = min(quantity, available_capacity, LIMIT)  # Ensure not buying more than allowed
        elif quantity < 0:  # Selling
            available_capacity = -LIMIT - current_position
            quantity_to_order = max(quantity, available_capacity, -LIMIT)  # Ensure not selling more than held

        order = Order(product, price, quantity_to_order)
        assert (order is not None), f"Order not placed for {product} at {price} and quantity {quantity_to_order}"
        self.position[product] += quantity_to_order
        print(f'BOUGHT {quantity_to_order} {product} at {price} (current position: {self.position[product]})') if quantity_to_order > 0 else print(f'SOLD {quantity_to_order} {product} at {price} (current position: {self.position[product]})')
        return order

    def calc_next_price_regression(self, product):

        SMOOTHING = 0.99
        smoothed_cache = self.smooth_data(self.caches[product], SMOOTHING)
        a,b,c,d,intercept = np.polyfit(range(0, len(smoothed_cache)), smoothed_cache, 4)
        
        t = len(self.caches[product]) + self.window_sizes[product]/4
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
    def execute_regression_trades(self, product, state, cache: list, window_size, results):
        while len(cache) >= window_size:
            cache.pop(0)
        bid, bid_vol, ask, ask_vol = self.get_best_prices(state.order_depths[product])
        cache.append((bid + ask) / 2)

        lower_band = -(1e9)
        upper_band = 1e9
        if len(cache) == window_size:
            lower_band = self.calc_next_price_regression(product) - 1.0
            upper_band = self.calc_next_price_regression(product) + 1.0
            orders = self.create_orders_regression(product, state.order_depths[product], lower_band, upper_band, 250)
            results[product] = orders


    
    def run(self, state: TradingState):
        INF = int(1e9)
        conversions = 1
        results = defaultdict(list)

        if state.traderData:
            # Decode the saved state
            saved_state = jsonpickle.decode(state.traderData)
            # Directly access attributes from the saved_state
            self.position = saved_state.position
            self.caches = saved_state.caches
            self.window_sizes = saved_state.window_sizes
            self.position_limits = saved_state.position_limits
            self.SMOOTHING = saved_state.SMOOTHING


        # Update positions based on the current state and ensure it is valid
        for product in state.order_depths:
            self.position[product] = state.position.get(product, 0)
            assert(self.position[product] <= self.position_limits[product] or self.position[product] >= -self.position_limits[product]), f"Position limit exceeded for {product} at {state.timestamp}"

        if 'CHOCOLATE' in state.order_depths.keys():
            self.execute_regression_trades('CHOCOLATE', state,self.caches['CHOCOLATE'], self.window_sizes['CHOCOLATE'], results)

        
        return results, conversions, jsonpickle.encode(self)
