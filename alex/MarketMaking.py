import jsonpickle
import numpy as np
import pandas as pd
from datamodel import TradingState, OrderDepth, Order

class Trader:

    def __init__(self):
        self.position_open = {'STARFRUIT': False}

    def run (self, state : TradingState):

        if state.traderData:
            savedData = jsonpickle.decode(state.traderData)
            self.position_open = savedData.position_open
        
        conversions = 1
        result = {}
        product = 'STARFRUIT'

        orders = []
        orderDepth = state.order_depths[product]

        ap1 = min(orderDepth.sell_orders)
        bp1 = max(orderDepth.buy_orders)
        # av1 = orderDepth.sell_orders[ap1]
        # bv1 = orderDepth.buy_orders[bp1]

        if len(orderDepth.sell_orders) > 1:
            keys = list(orderDepth.sell_orders.keys())
            keys.sort(reverse=True)
            ap2 = keys[1]
            # av2 = orderDepth.sell_orders[ap2]
        else:
            ap2 = None
            # av2 = None

        if len(orderDepth.buy_orders) > 1:
            keys = list(orderDepth.buy_orders.keys())
            keys.sort()
            bp2 = keys[1]
            # bv2 = orderDepth.buy_orders[bp2]
        else:
            bp2 = None
            # bv2 = None

        if not self.position_open[product] and ap2:
            # open long position
            orders.append(Order(product, (ap1 + 1), 1))
            self.position_open[product] = True
            print("Long position opened for product: ", product, " at price: ", ap1)

        elif self.position_open[product] and bp2:   # close long position
            orders.append(Order(product, (bp1 - 1), -1))
            self.position_open[product] = False
            print("Long position closed for product: ", product, " at price: ", bp1)


            result[product] = orders
                
        traderData = jsonpickle.encode(self)

        return result, conversions, traderData

    