import jsonpickle
import numpy as np
import pandas as pd
from datamodel import TradingState, Order
from typing import List
from collections import defaultdict
import collections

class Trader:
    def __init__(self):
        self.something = 0

    def run(self, state: TradingState):
        
        if state.traderData:
            saved_state = jsonpickle.decode(state.traderData)
            self.something = saved_state.something


        print('Position: ',  state.position.get('STARFRUIT', 0))
        

        conversions = 1
        results = defaultdict(list)

        star_order_depths = state.order_depths['STARFRUIT']
        
        osell = collections.OrderedDict(sorted(star_order_depths.sell_orders.items()))
        obuy = collections.OrderedDict(sorted(star_order_depths.buy_orders.items(), reverse=True))

        best_bid = list(obuy.keys())[0]
        best_ask = list(osell.keys())[0]

        best_bid_2 = list(obuy.keys())[1] if len(obuy) > 1 else 0
        best_ask_2 = list(osell.keys())[1] if len(osell) > 1 else 0

        results['STARFRUIT'].append(Order('STARFRUIT', (best_ask - 1), 1))

        return results, conversions, jsonpickle.encode(self)

