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
        self.position = {'STARFRUIT': 0, 'AMETHYSTS': 0, 'ORCHIDS': 0, 'CHOCOLATE': 0, 'STRAWBERRIES': 0, 'ROSES': 0, 'GIFT_BASKET': 0}
        # BASKET
        self.position_limits = {'CHOCOLATE': 250, 'STRAWBERRIES': 350, 'ROSES': 60, 'GIFT_BASKET': 58}
        self.basket_mid_prices = {'CHOCOLATE': [], 'STRAWBERRIES': [], 'ROSES': [], 'GIFT_BASKET': []}
        self.spread = []


    def get_best_prices(self, order_depth):
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

    def calculate_component_cost(self, prices):
        components = ['CHOCOLATE', 'STRAWBERRIES', 'ROSES']
        quantities = [4, 6, 1]  # Example quantities needed for a basket
        total_cost = 0
        min_volume_supported = float('inf')

        for component, qty in zip(components, quantities):
            price_info = prices.get(component, {'ask': float('inf'), 'ask_volume': 0})
            ask_price = price_info.get('ask', float('inf'))
            ask_volume = max(0, price_info.get('ask_volume', 0))  # Treat negative volumes as zero
            cost = ask_price * qty
            total_cost += cost

            if ask_volume >= qty:
                volume_supported = ask_volume // qty
                min_volume_supported = min(min_volume_supported, volume_supported)
            else:
                min_volume_supported = 0  # Set to zero if any component volume is insufficient
                print(f"Volume issue with {component}: Required {qty}, Available {ask_volume}")

        return total_cost, min_volume_supported
    
    def check_arbitrage_opportunity(self, prices):
        aribtrage_details = []
        arbitrage = False
        if len(self.spread) >= 12:
            spread_rolling_mean = np.mean(self.spread[-12:])
            spread_rolling_std = np.std(self.spread[-12:])
            upper_band = spread_rolling_mean + 2 * spread_rolling_std
            lower_band = spread_rolling_mean - 2 * spread_rolling_std
        
            if self.spread[-1] > 480 and self.position['GIFT_BASKET'] == 0:
                # sell 1 basket / buy 4 chocolate, 6 strawberries, 1 rose
                aribtrage_details.append({
                    'action': 'sell',
                    'product': 'GIFT_BASKET',
                    'quantity': 1
                })
                aribtrage_details.append({
                    'action': 'buy',
                    'product': 'CHOCOLATE',
                    'quantity': 4
                })
                aribtrage_details.append({
                    'action': 'buy',
                    'product': 'STRAWBERRIES',
                    'quantity': 6
                })
                aribtrage_details.append({
                    'action': 'buy',
                    'product': 'ROSES',
                    'quantity': 1
                })
                arbitrage = True
                
            elif self.spread[-1] < 320 and self.position['GIFT_BASKET'] == 0:
                # buy 1 basket / sell 4 chocolate, 6 strawberries, 1 rose
                aribtrage_details.append({
                    'action': 'buy',
                    'product': 'GIFT_BASKET',
                    'quantity': 1
                })
                aribtrage_details.append({
                    'action': 'sell',
                    'product': 'CHOCOLATE',
                    'quantity': 4
                })
                aribtrage_details.append({
                    'action': 'sell',
                    'product': 'STRAWBERRIES',
                    'quantity': 6
                })
                aribtrage_details.append({
                    'action': 'sell',
                    'product': 'ROSES',
                    'quantity': 1
                })
                arbitrage = True
            elif self.spread[-1] < 430 and self.spread[-1] > lower_band and self.position['GIFT_BASKET'] < 0:
                # buy 1 basket / sell 4 chocolate, 6 strawberries, 1 rose
                aribtrage_details.append({
                    'action': 'buy',
                    'product': 'GIFT_BASKET',
                    'quantity': 1
                })
                aribtrage_details.append({
                    'action': 'sell',
                    'product': 'CHOCOLATE',
                    'quantity': 4
                })
                aribtrage_details.append({
                    'action': 'sell',
                    'product': 'STRAWBERRIES',
                    'quantity': 6
                })
                aribtrage_details.append({
                    'action': 'sell',
                    'product': 'ROSES',
                    'quantity': 1
                })
                arbitrage = True
            elif self.spread[-1] > 380 and self.spread[-1] < upper_band and self.position['GIFT_BASKET'] > 0:
                # sell 1 basket / buy 4 chocolate, 6 strawberries, 1 rose
                aribtrage_details.append({
                    'action': 'sell',
                    'product': 'GIFT_BASKET',
                    'quantity': 1
                })
                aribtrage_details.append({
                    'action': 'buy',
                    'product': 'CHOCOLATE',
                    'quantity': 4
                })
                aribtrage_details.append({
                    'action': 'buy',
                    'product': 'STRAWBERRIES',
                    'quantity': 6
                })
                aribtrage_details.append({
                    'action': 'buy',
                    'product': 'ROSES',
                    'quantity': 1
                })
                arbitrage = True
            
            else:
                print("Not enough data points to calculate spread statistics.")

        return arbitrage, aribtrage_details

    def execute_basket_trades(self, state, results):
        orders = []
        prices = {}

        # Extract price and volume information for each product from order depths
        for product in ['CHOCOLATE', 'STRAWBERRIES', 'ROSES', 'GIFT_BASKET']:
            order_depth = state.order_depths[product]
            best_bid, best_bid_volume, best_ask, best_ask_volume = self.get_best_prices(order_depth)
            prices[product] = {'bid': best_bid, 'bid_volume': best_bid_volume, 'ask': best_ask, 'ask_volume': best_ask_volume, 'mid':( (best_bid + best_ask) / 2)}

        real_value_gb = 4 * prices['CHOCOLATE']['mid'] + 6 * prices['STRAWBERRIES']['mid'] + prices['ROSES']['mid']
        self.spread.append(prices['GIFT_BASKET']['mid'] - real_value_gb)

        for product in self.basket_mid_prices:
            self.basket_mid_prices[product].append(prices[product]['mid'])

        # Check if the required volume of all instruments is the minimum required (1 basket, 1 rose, 4 chocolate, 6 strawberry)
        if prices['GIFT_BASKET']['bid_volume'] < 1 or prices['ROSES']['ask_volume'] > -1 or prices['CHOCOLATE']['ask_volume'] > -4 or prices['STRAWBERRIES']['ask_volume'] > -6:
            print("Required volume of all instruments is not met. No trades executed.")
            return orders

        # Check for arbitrage opportunity
        arbitrage, details = self.check_arbitrage_opportunity(prices)
        if arbitrage:
            for detail in details:
                action = detail['action']
                product = detail['product']
                quantity = detail['quantity']
                if action == 'sell':
                    # Trade exactly one unit of basket and equivalent volumes of each component
                    prod_order = self.place_order(product, prices[product]['bid'], -quantity)
                    results[product] = prod_order       
                elif action == 'buy':
                    # Buy the basket and sell the equivalent components
                    prod_order = self.place_order(product, prices[product]['ask'], quantity)
                    results[product] = prod_order
        else:
            print("No arbitrage opportunity found; no trades executed.")
        
        print("Summary of positions after trade execution:")
        for product, qty in self.position.items():
            print(f"{product}: {qty}")
        return orders

    def place_order(self, product, price, quantity):
        orders = []
        current_position = self.position[product]
        LIMIT = self.position_limits[product]
        if quantity > 0:  # Buying
            available_capacity = LIMIT - current_position
            quantity_to_order = min(quantity, available_capacity, LIMIT)
        else:  # Selling
            available_capacity = -LIMIT - current_position  # You can sell only what you currently hold
            quantity_to_order = max(quantity, available_capacity, -LIMIT)  # Ensure not selling more than held

        orders.append(Order(product, price, quantity_to_order))
        self.position[product] += quantity_to_order
        print(f'BOUGHT {quantity_to_order} {product} at {price} (current position: {self.position[product]})') if quantity_to_order > 0 else print(f'SOLD {quantity_to_order} {product} at {price} (current position: {self.position[product]})')
        return orders

    def run(self, state: TradingState):
        INF = int(1e9)
        conversions = 1
        result = {}

        if state.traderData:
            # Decode the saved state
            saved_state = jsonpickle.decode(state.traderData)
            # Directly access attributes from the saved_state
            self.position = saved_state.position
            self.position_limits = saved_state.position_limits
            self.spread = saved_state.spread
            self.basket_mid_prices = saved_state.basket_mid_prices

        # Update positions based on the current state
        for product in state.order_depths:
            self.position[product] = state.position.get(product, 0)
            print(f"INITIAL POSITIONS {product}: {self.position[product]}")
            
        if all(item in state.order_depths for item in ['CHOCOLATE', 'STRAWBERRIES', 'ROSES', 'GIFT_BASKET']):
            self.execute_basket_trades(state, result)
        
        return result, conversions, jsonpickle.encode(self)
