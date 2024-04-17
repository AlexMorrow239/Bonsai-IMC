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
        self.position_limits = {'STARFRUIT': 20, 'AMETHYSTS': 20, 'ORCHIDS': 100, 'CHOCOLATE': 232, 'STRAWBERRIES': 348, 'ROSES': 58, 'GIFT_BASKET': 58}
        self.basket_mid_prices = {'CHOCOLATE': [], 'STRAWBERRIES': [], 'ROSES': [], 'GIFT_BASKET': []}
        self.spread = []
        self.basket_components = {'CHOCOLATE': 4, 'STRAWBERRIES': 6, 'ROSES': 1, 'GIFT_BASKET': 1} # Components of one basket and the corresponding proportions


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
    
    def calculate_unit_volume(self, prices):

        can_buy = can_sell = False  # Flags to check if all components can be bought/sold
        # Initialize dictionaries to store the number of units to trade for each product, and the volume of each product to trade based on the quantity of product in one unit of the basket
        buy_units_per_prod = sell_units_per_prod = product_buy_volume = product_sell_volume = {'CHOCOLATE': 0, 'STRAWBERRIES': 0, 'ROSES': 0, 'GIFT_BASKET': 0}
        
        # ALL VOLUMES WILL BE POSITIVE, adjust signs directly in arbitrage_details
        # Buying components, selling basket
        for product, unit in self.basket_components.items():
            if product != 'GIFT_BASKET':
                buy_units_per_prod[product] = (-1 * prices[product]['ask_volume']) // self.basket_components[product]   # Gift Basket is opposite action of the components
            else:
                buy_units_per_prod[product] = prices[product]['bid_volume'] // self.basket_components[product]
        if all(buy_units_per_prod[product] != 0 for product in buy_units_per_prod.keys()):
            can_buy = True
        else:
            print("Cannot BUY components due to insufficient volume")
                
        # Selling components, buying basket
        for product, unit in self.basket_components.items():
            if product != 'GIFT_BASKET':
                sell_units_per_prod[product] = prices[product]['bid_volume'] // self.basket_components[product]     # Gift Basket is opposite action of the components
            else:
                sell_units_per_prod[product] = (-1 * prices[product]['ask_volume']) // self.basket_components[product]
        
        if all(sell_units_per_prod[product] != 0 for product in sell_units_per_prod.keys()):
            can_sell = True
        else:
            print("Cannot SELL components due to insufficient volume")
        
        # Calculate number of units to trade based on the product with the least amount of tradable units
        buy_units = sell_units = 0
        if can_buy:
            buy_units = min(buy_units_per_prod.values())
            print(f"Arbitrage opportunity: Buy {buy_units} units of components")
        if can_sell:
            sell_units = min(sell_units_per_prod.values())
            print(f"Arbitrage opportunity: Sell {sell_units} units of components")
        
        # Calculate the volume of each product to trade based on the quantity of product in one unit of the basket
        for product, unit in self.basket_components.items():
            product_buy_volume[product] = (unit * buy_units)
            product_sell_volume[product] = (unit * sell_units)
        
        # Filter down volumes if maximum position limits are reached
        for product, unit in self.basket_components.items():
            
            cur_prod_position = self.position[product]
            
            if product != 'GIFT_BASKET':
                # If short position and buying, check if volume exceeds position limit
                if cur_prod_position < 0:
                    # Only change selling dict because we are selling the product
                    max_sell_volume = self.position_limits[product] + self.position[product]
                    if max_sell_volume == 0:
                        product_sell_volume = {'CHOCOLATE': 0, 'STRAWBERRIES': 0, 'ROSES': 0, 'GIFT_BASKET': 0}
                    elif product_sell_volume[product] > max_sell_volume:
                        while product_sell_volume[product] > max_sell_volume:
                            for product2, unit2 in self.basket_components.items():  # Adjust all components down one basket unit
                                product_sell_volume[product2] -= unit2
                        assert(product_sell_volume[product] <= 0), f"Negative SELL Volume of {product_sell_volume[product]} for product {product} after adjusting for position limits"
                        assert(product_sell_volume[product] % unit == 0), f"SELL Volume of {product_sell_volume[product]} for product {product} not a multiple of {unit} after adjusting for position limits"
                # If long position and selling, check if volume exceeds position limit
                elif cur_prod_position > 0:
                    # Only change buying dict because we are buying the product
                    max_buy_volume = self.position_limits[product] - self.position[product]
                    if max_buy_volume == 0:
                        product_buy_volume = {'CHOCOLATE': 0, 'STRAWBERRIES': 0, 'ROSES': 0, 'GIFT_BASKET': 0}
                    elif product_buy_volume[product] > max_buy_volume:
                        while product_buy_volume[product] > max_buy_volume:
                            for product2, unit2 in self.basket_components.items():  # Adjust all components down one basket unit
                                product_buy_volume[product2] -= unit2
                        assert(product_buy_volume[product] >= 0), f"Negative BUY Volume of {product_buy_volume[product]} for product {product} after adjusting for position limits position: {cur_prod_position}"
                        assert(product_buy_volume[product] % unit == 0), f"BUY Volume of {product_buy_volume[product]} for product {product} not a multiple of {unit} after adjusting for position limits"
                    else:
                        continue    # Otherwise do nothing because we can go all the way up to the position limits
                
            elif product == 'GIFT_BASKET':  # GIFT BASKET is special case, opposite action of the components
                if cur_prod_position > 0:
                    max_buy_volume_for_sell_components = self.position_limits[product] - self.position[product]
                    if max_buy_volume_for_sell_components == 0:
                        product_sell_volume = {'CHOCOLATE': 0, 'STRAWBERRIES': 0, 'ROSES': 0, 'GIFT_BASKET': 0}
                    elif product_sell_volume[product] > max_buy_volume_for_sell_components:
                        while product_sell_volume[product] > max_buy_volume_for_sell_components:
                            for product2,unit2 in self.basket_components.items():
                                product_sell_volume[product2] -= unit2
                        assert(product_sell_volume[product] <= 0), f"Negative SELL Volume of {product_sell_volume[product]} for product {product} after adjusting for position limits"
                        assert(product_sell_volume[product] % unit == 0), f"SELL Volume of {product_sell_volume[product]} for product {product} not a multiple of {unit} after adjusting for position limits"
                elif cur_prod_position < 0:
                    max_sell_volume_for_buy_components = self.position_limits[product] + self.position[product]
                    if max_sell_volume_for_buy_components == 0:
                        product_buy_volume = {'CHOCOLATE': 0, 'STRAWBERRIES': 0, 'ROSES': 0, 'GIFT_BASKET': 0}
                    elif product_buy_volume[product] > max_sell_volume_for_buy_components:
                        while product_buy_volume[product] > max_sell_volume_for_buy_components:
                            for product2, unit2 in self.basket_components.items():
                                product_buy_volume[product2] -= unit2
                        assert(product_buy_volume[product] >= 0), f"Negative BUY Volume of {product_buy_volume[product]} for product {product} after adjusting for position limits"
                        assert(product_buy_volume[product] % unit == 0), f"BUY Volume of {product_buy_volume[product]} for product {product} not a multiple of {unit} after adjusting for position limits"
                    else:
                        continue    # Otherwise do nothing because we can go all the way up to the position limits
                
        return product_buy_volume, product_sell_volume

    def check_arbitrage_opportunity(self, prices):
        # Calculate the volume of each product to trade based on the quantity of product in one unit of the basket and the available volumes
        product_buy_volume, product_sell_volume = self.calculate_unit_volume(prices)
        can_buy = all(product_buy_volume[product] != 0 for product in product_buy_volume.keys())
        can_sell = all(product_sell_volume[product] != 0 for product in product_buy_volume.keys())
        
        aribtrage_details = []
        arbitrage = False
        if len(self.spread) >= 48:
            spread_rolling_mean = np.mean(self.spread[-48:])
            spread_rolling_std = np.std(self.spread[-48:])
            upper_band = spread_rolling_mean + 3.1 * spread_rolling_std
            lower_band = spread_rolling_mean - 3.1 * spread_rolling_std
        
            if self.spread[-1] > upper_band and self.position['GIFT_BASKET'] == 0 and can_buy:
                # sell 1 basket / buy 4 chocolate, 6 strawberries, 1 rose
                aribtrage_details.append({
                    'action': 'sell',
                    'product': 'GIFT_BASKET',
                    'quantity': (-1 * product_buy_volume['GIFT_BASKET'])
                })
                aribtrage_details.append({
                    'action': 'buy',
                    'product': 'CHOCOLATE',
                    'quantity': product_buy_volume['CHOCOLATE']
                })
                aribtrage_details.append({
                    'action': 'buy',
                    'product': 'STRAWBERRIES',
                    'quantity': product_buy_volume['STRAWBERRIES']
                })
                aribtrage_details.append({
                    'action': 'buy',
                    'product': 'ROSES',
                    'quantity': product_buy_volume['ROSES']
                })
                arbitrage = True
                
            elif self.spread[-1] < lower_band and self.position['GIFT_BASKET'] == 0 and can_sell:
                # buy 1 basket / sell 4 chocolate, 6 strawberries, 1 rose
                aribtrage_details.append({
                    'action': 'buy',
                    'product': 'GIFT_BASKET',
                    'quantity': product_sell_volume['GIFT_BASKET']
                })
                aribtrage_details.append({
                    'action': 'sell',
                    'product': 'CHOCOLATE',
                    'quantity': (-1 * product_sell_volume['CHOCOLATE'])
                })
                aribtrage_details.append({
                    'action': 'sell',
                    'product': 'STRAWBERRIES',
                    'quantity': (-1 * product_sell_volume['STRAWBERRIES'])
                })
                aribtrage_details.append({
                    'action': 'sell',
                    'product': 'ROSES',
                    'quantity': (-1 * product_sell_volume['ROSES'])
                })
                arbitrage = True
            elif self.spread[-1] < lower_band and self.spread[-1] > lower_band and self.position['GIFT_BASKET'] < 0 and can_sell:
                # buy 1 basket / sell 4 chocolate, 6 strawberries, 1 rose
                aribtrage_details.append({
                    'action': 'buy',
                    'product': 'GIFT_BASKET',
                    'quantity': product_sell_volume['GIFT_BASKET']
                })
                aribtrage_details.append({
                    'action': 'sell',
                    'product': 'CHOCOLATE',
                    'quantity': (-1 * product_sell_volume['CHOCOLATE'])
                })
                aribtrage_details.append({
                    'action': 'sell',
                    'product': 'STRAWBERRIES',
                    'quantity': (-1 * product_sell_volume['STRAWBERRIES'])
                })
                aribtrage_details.append({
                    'action': 'sell',
                    'product': 'ROSES',
                    'quantity': (-1 * product_sell_volume['ROSES'])
                })
                arbitrage = True
            elif self.spread[-1] > upper_band and self.spread[-1] < upper_band and self.position['GIFT_BASKET'] > 0 and can_buy:
                # sell 1 basket / buy 4 chocolate, 6 strawberries, 1 rose
                aribtrage_details.append({
                    'action': 'sell',
                    'product': 'GIFT_BASKET',
                    'quantity': (-1 * product_buy_volume['GIFT_BASKET'])
                })
                aribtrage_details.append({
                    'action': 'buy',
                    'product': 'CHOCOLATE',
                    'quantity': product_buy_volume['CHOCOLATE']
                })
                aribtrage_details.append({
                    'action': 'buy',
                    'product': 'STRAWBERRIES',
                    'quantity': product_buy_volume['STRAWBERRIES']
                })
                aribtrage_details.append({
                    'action': 'buy',
                    'product': 'ROSES',
                    'quantity': product_buy_volume['ROSES']
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
                    prod_order = self.place_order(product, prices[product]['bid'], -quantity)
                    assert (quantity % self.basket_components[product] == 0), f"Quantity {quantity} not a multiple of {self.basket_components[product]}"
                    print(f"SELLING {quantity} {product} at {prices[product]['bid']}")
                    results[product] = prod_order       
                elif action == 'buy':
                    prod_order = self.place_order(product, prices[product]['ask'], quantity)
                    assert (quantity % self.basket_components[product] == 0), f"Quantity {quantity} not a multiple of {self.basket_components[product]} for {product} at {state.timestamp}"
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
            quantity_to_order = min(quantity, available_capacity, LIMIT)  # Ensure not buying more than allowed
        elif quantity < 0:  # Selling
            available_capacity = -LIMIT - current_position
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
            self.basket_components = saved_state.basket_components

        # Update positions based on the current state and ensure it is valid
        for product in state.order_depths:
            self.position[product] = state.position.get(product, 0)
            assert(self.position[product] <= self.position_limits[product] or self.position[product] >= -self.position_limits[product]), f"Position limit exceeded for {product} at {state.timestamp}"
            print(f"INITIAL POSITIONS {product}: {self.position[product]}")
        for product, unit in self.basket_components.items():
            assert(self.position[product] % unit == 0), f"Position of {product} not a multiple of {unit} at {state.timestamp}"

        if all(item in state.order_depths for item in ['CHOCOLATE', 'STRAWBERRIES', 'ROSES', 'GIFT_BASKET']):
            self.execute_basket_trades(state, result)
        
        return result, conversions, jsonpickle.encode(self)
