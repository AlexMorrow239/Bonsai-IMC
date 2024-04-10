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
    def __init__ (self):
        self.empty_dict = {'STARFRUIT': 0, 'AMETHYSTS': 0}
        self.position = copy.deepcopy(self.empty_dict)
        self.star_cache = []
        self.star_window_size = 4
        self.INF = int(1e9)
        

    def values_extract(self, order_dict, buy=0):
            tot_vol = 0
            best_val = -1
            mxvol = -1

            for ask, vol in order_dict.items():
                if(buy==0):
                    vol *= -1
                tot_vol += vol
                if tot_vol > mxvol:
                    mxvol = vol
                    best_val = ask
            
            return tot_vol, best_val

    def calc_next_price(self):
        # Data from 4 days (possible overfitting)
        # coef = [3.72536029254, -1.613913639929, -5.209307802657288, 0.00943688103602776]
        # intercept = 4959.376030787304

        # Data from 1 day
        coef = [2.194822134563818, -3.526493888652451, 1.8195854259998546, -0.0002055528195619442]
        intercept = 5035.728800687614
        next_price = intercept

        for i, val in enumerate(self.star_cache):
            next_price += val * coef[i]
        
        return int(round(next_price))
    
    def create_orders_regression(self, product, ordder_depth, acc_bid, acc_ask, LIMIT):
        orders: list[Order] = []

        osell = collections.OrderedDict(sorted(ordder_depth.sell_orders.items()))
        obuy = collections.OrderedDict(sorted(ordder_depth.buy_orders.items(), reverse=True))

        cum_vol__sell, best_sell = self.values_extract(osell)
        cum_vol_buy, best_buy = self.values_extract(obuy, 1)

        cur_position = self.position.get(product, 0)

        for ask, vol in osell.items():
            if((ask <= acc_bid) or ((cur_position < 0) and (ask == acc_bid + 1))) and cur_position < LIMIT:
                quantity = min(-vol, LIMIT, -cur_position)
                cur_position += quantity
                orders.append(Order(product, ask, quantity))

        undercut_buy = best_buy + 1
        undercut_sell = best_sell - 1

        bid_price = min(undercut_buy, acc_bid)
        ask_price = max(undercut_sell, acc_ask)
            
        if (cur_position > LIMIT):
            quantity = LIMIT - cur_position
            orders.append(Order(product, bid_price, quantity))
            cur_position += quantity
        
        cur_position = self.position.get(product, 0)

        for bid, vol in obuy.items():
            if((bid >= acc_ask) or ((cur_position > 0) and ((bid + 1) == acc_ask))) and cur_position > -LIMIT:
                quantity = max(-vol, (-LIMIT - cur_position))
                cur_position += quantity
                orders.append(Order(product, bid, quantity))
        
        if cur_position > -LIMIT:
            quantity = -LIMIT - cur_position
            orders.append(Order(product, ask_price, quantity))
            cur_position += quantity
        
        return orders

    def run(self, state: TradingState):
        conversions = 1
        result = {}

        if state.traderData:
            saved_state = jsonpickle.decode(state.traderData)
            self.position = saved_state.position
            self.star_cache = saved_state.star_cache
            self.star_window_size = saved_state.star_window_size
            self.INF = saved_state.INF
            self.empty_dict = saved_state.empty_dict



        if len(self.star_cache) == self.star_window_size:
            self.star_cache.pop(0)

        _, star_best_sell = self.values_extract(collections.OrderedDict(sorted(state.order_depths['STARFRUIT'].sell_orders.items())))
        _, star_best_buy = self.values_extract(collections.OrderedDict(sorted(state.order_depths['STARFRUIT'].buy_orders.items(), reverse=True)), 1)

        self.star_cache.append((star_best_sell + star_best_buy) / 2)

        star_band_lower = self.INF
        star_band_upper = self.INF

        if len(self.star_cache) == self.star_window_size:
            star_band_lower = self.calc_next_price() - 1
            star_band_upper = self.calc_next_price() + 1

        star_orders = self.create_orders_regression('STARFRUIT', state.order_depths['STARFRUIT'], star_band_lower, star_band_upper, 20)
        result['STARFRUIT'] = star_orders

        traderData = jsonpickle.encode(self)

        return result, conversions, traderData


        
                                        
        
        