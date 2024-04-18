from typing import Dict, List, Tuple, Any, Union
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
        self.position = {'STARFRUIT': 0, 'AMETHYSTS': 0, 'ORCHIDS': 0, 'CHOCOLATE': 0, 'STRAWBERRIES': 0, 'ROSES': 0, 'GIFT_BASKET': 0}
        self.position_limits = {'STARFRUIT': 20, 'AMETHYSTS': 20, 'ORCHIDS': 100, 'CHOCOLATE': 232, 'STRAWBERRIES': 348, 'ROSES': 58, 'GIFT_BASKET': 58}
        # STARFRUIT
        self.star_cache = []
        self.star_window_size = 8
        # AMETHYSTS
        self.am_remaining_quantity = 0
        self.am_partially_closed = False
        self.am_latest_price = 0
        #BASKET
        self.basket_mid_prices = {'CHOCOLATE': [], 'STRAWBERRIES': [], 'ROSES': [], 'GIFT_BASKET': []}
        self.spread = []
        self.basket_components = {'CHOCOLATE': 4, 'STRAWBERRIES': 6, 'ROSES': 1, 'GIFT_BASKET': 1} # Components of one basket and the corresponding proportions
        self.partially_closed = False

    def run(self, state: TradingState):
        conversions = 1
        result = {}
        if state.traderData:
            saved_state = jsonpickle.decode(state.traderData)
            #Global
            self.position = saved_state.position
            self.position_limits = saved_state.position_limits
            # STARFRUIT
            self.star_cache = saved_state.star_cache
            self.star_window_size = saved_state.star_window_size
            # AMETHYSTS
            self.am_remaining_quantity = saved_state.am_remaining_quantity
            self.am_partially_closed = saved_state.am_partially_closed
            self.am_latest_price = saved_state.am_latest_price
            # BASKET
            self.basket_mid_prices = saved_state.basket_mid_prices
            self.spread = saved_state.spread
            self.basket_components = saved_state.basket_components
            self.partially_closed = saved_state.partially_closed
        # Update positions for each procuct
        for product in state.order_depths:
            self.position[product] = state.position.get(product, 0) # Update position
        if 'STARFRUIT' in state.order_depths.keys():
            self.execute_starfruit_trades(state.order_depths['STARFRUIT'], result)
        if 'AMETHYSTS' in state.order_depths.keys() and state.timestamp > 2000: 
            self.execute_amethysts_trades(state.order_depths['AMETHYSTS'], result)
        if all(item in state.order_depths.keys() for item in ['CHOCOLATE', 'STRAWBERRIES', 'ROSES', 'GIFT_BASKET']):
            self.execute_basket_trades(state, result)
        
        print(f"RESULTS: {result}")
        return result, conversions, jsonpickle.encode(self)

# HELPER FUNCTIONS----------------------------------------------------------------------------------------------------------------------------
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

# AMETHYSTS----------------------------------------------------------------------------------------------------------------------------
    def execute_amethysts_trades(self, am_order_depth, results):
        am_live_bid_price, am_live_bid_volume, am_live_ask_price, am_live_ask_volume = self.get_best_prices(am_order_depth)
        am_orders = []
        am_cur_position = self.position['AMETHYSTS']

        if am_cur_position == 0:
            am_orders = self.open_order_high_frequency(am_live_bid_price, am_live_ask_price, am_live_bid_volume, am_live_ask_volume)
        elif am_cur_position != 0 and not self.am_partially_closed:
            am_orders = self.handle_not_partially_closed_high_frequency('AMETHYSTS', am_live_ask_price, am_live_bid_price, am_live_ask_volume, am_live_bid_volume)            
        elif am_cur_position != 0 and self.am_partially_closed:
            am_orders = self.handle_partially_closed_high_frequency('AMETHYSTS', am_live_ask_price, am_live_bid_price, am_live_ask_volume, am_live_bid_volume)
        results['AMETHYSTS'] = am_orders
    
    def open_order_high_frequency(self, best_bid, best_ask, best_bid_volume, best_ask_volume):
        orders = []
        if best_bid > 10000:
            am_open_order_volume = min(abs(best_bid_volume)+3, 20)
            orders.append(Order('AMETHYSTS', best_bid-1, -am_open_order_volume))
            self.am_latest_price = best_bid
            self.am_remaining_quantity = am_open_order_volume
            self.position['AMETHYSTS'] -= am_open_order_volume
        elif best_ask < 10000:
            am_open_order_volume = min(abs(best_ask_volume)+3, 20)
            orders.append(Order('AMETHYSTS', best_ask+1, am_open_order_volume))
            self.am_latest_price = best_ask
            self.am_remaining_quantity = am_open_order_volume
            self.position['AMETHYSTS'] += am_open_order_volume
        return orders
    
    def handle_not_partially_closed_high_frequency(self, product, ask_price, bid_price, ask_volume, bid_volume):

        orders = []
        current_position = self.position[product]
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
    
    def handle_partially_closed_high_frequency(self, product, ask_price, bid_price, ask_volume, bid_volume):
        orders = []
        current_position = self.position[product]
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

# STARFRUIT----------------------------------------------------------------------------------------------------------------------------
    def execute_starfruit_trades(self, star_order_depth, results):
        if len(self.star_cache) == self.star_window_size:
            self.star_cache.pop(0)  # Remove the oldest price from the cache
        star_best_buy, bv, star_best_sell, sv = self.get_best_prices(star_order_depth)
        self.star_cache.append((star_best_sell + star_best_buy) / 2)    # Append the mid price to the cache

        star_band_lower = -(1e9)
        star_band_upper = (1e9)
        if len(self.star_cache) == self.star_window_size:
            # Use predicted next price to determine acceptable bids and asks
            star_band_lower = self.calc_next_price_regression() - 1.0
            star_band_upper = self.calc_next_price_regression() + 1.0
            star_orders = self.create_orders_regression('STARFRUIT', star_order_depth, star_band_lower, star_band_upper, 19)
            results['STARFRUIT'] = star_orders
        else:
            print("Not enough data for STARFRUIT.")

    
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

# BASKET----------------------------------------------------------------------------------------------------------------------------
    def execute_basket_trades(self, state: TradingState, results: Dict[str, List[Order]]) ->Tuple[Dict[str, List[Order]], int, Any | None]:
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

        # Check if the basket is partially closed and handle it
        self.handle_partial_close(state, prices, results)

        # Check for arbitrage opportunity
        arbitrage, details = self.check_arbitrage_opportunity(prices)
        if  not arbitrage:
            print("No arbitrage opportunity detected.")
            return
        
        for detail in details:
            action = detail['action']
            product = detail['product']
            quantity = detail['quantity']
            if action == 'sell':
                prod_order = self.place_order(product, prices[product]['bid'], -quantity)
                assert (quantity % self.basket_components[product] == 0), f"Quantity {quantity} not a multiple of {self.basket_components[product]}"
                print(f"SELLING {quantity} {product} at {prices[product]['bid']}") 
            elif action == 'buy':
                prod_order = self.place_order(product, prices[product]['ask'], quantity)
                assert (quantity % self.basket_components[product] == 0), f"Quantity {quantity} not a multiple of {self.basket_components[product]} for {product} at {state.timestamp}"
            if product in results.keys():
                results[product].append(prod_order)
            else:
                results[product] = [prod_order]

        print("Summary of positions after trade execution:")
        for product, qty in self.position.items():
            print(f"{product}: {qty}")
    
    def calculate_unit_volume(self, prices: Dict[str, Dict[str, int]]) -> Tuple[Dict[str, int], Dict[str, int] ]:

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
    
    def check_arbitrage_opportunity(self, prices: Dict[str, Dict[str, int]]) -> Tuple[bool, List[Dict[str, Union[int, str]]]]:
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
                # upper open
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
                self.partially_closed = False
                
            elif self.spread[-1] < lower_band and self.position['GIFT_BASKET'] == 0 and can_sell:
                # buy 1 basket / sell 4 chocolate, 6 strawberries, 1 rose
                # lower open
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
                self.partially_closed = False
            elif self.spread[-1] < lower_band and self.spread[-1] > lower_band and self.position['GIFT_BASKET'] < 0 and can_sell:
                # buy 1 basket / sell 4 chocolate, 6 strawberries, 1 rose
                # upper close
                aribtrage_details.append({
                    'action': 'buy',
                    'product': 'GIFT_BASKET',
                    'quantity': -1 * (max(prices['GIFT_BASKET']['ask_volume'], self.position['GIFT_BASKET']))
                })
                aribtrage_details.append({
                    'action': 'sell',
                    'product': 'CHOCOLATE',
                    'quantity': -1 * (min((prices['CHOCOLATE']['bid_volume']), self.position['CHOCOLATE']))
                })
                aribtrage_details.append({
                    'action': 'sell',
                    'product': 'STRAWBERRIES',
                    'quantity': -1 * (min((prices['STRAWBERRIES']['bid_volume']), self.position['STRAWBERRIES']))
                })
                aribtrage_details.append({
                    'action': 'sell',
                    'product': 'ROSES',
                    'quantity': -1 * (min((prices['ROSES']['bid_volume']), self.position['ROSES']))
                })
                arbitrage = True
                self.partially_closed = True
            elif self.spread[-1] > upper_band and self.spread[-1] < upper_band and self.position['GIFT_BASKET'] > 0 and can_buy:
                # sell 1 basket / buy 4 chocolate, 6 strawberries, 1 rose
                # lower close
                aribtrage_details.append({
                    'action': 'sell',
                    'product': 'GIFT_BASKET',
                    'quantity': -1 * (min((prices['GIFT_BASKET']['bid_volume']), self.position['GIFT_BASKET']))
                })
                aribtrage_details.append({
                    'action': 'buy',
                    'product': 'CHOCOLATE',
                    'quantity': -1 * max(prices['CHOCOLATE']['ask_volume'], self.position['CHOCOLATE'])
                })
                aribtrage_details.append({
                    'action': 'buy',
                    'product': 'STRAWBERRIES',
                    'quantity': -1 * max(prices['STRAWBERRIES']['ask_volume'], self.position['STRAWBERRIES'])
                })
                aribtrage_details.append({
                    'action': 'buy',
                    'product': 'ROSES',
                    'quantity': -1 * max(prices['ROSES']['ask_volume'], self.position['ROSES'])
                })
                arbitrage = True
                self.partially_closed = True            
        else:
            print("Not enough data points to calculate spread statistics.")

        return arbitrage, aribtrage_details

    def handle_partial_close(self, state: TradingState, prices: Dict[str, Dict[str, int]], results: Dict[str, List[Order]]) -> Dict[str, List[Order]]:
        if self.partially_closed and all(self.position[product] == 0 for product in self.basket_components.keys()):
            self.partially_closed = False
        
        elif self.partially_closed:
            for product in self.basket_components.keys():
                if self.position[product] > 0:
                    quantity = -1 * min(self.position[product], prices[product]['bid_volume'])
                    assert (quantity < 0), f"Quantity {quantity} not less than 0 for {product} at {state.timestamp}"
                    prod_order = Order(product, prices[product]['bid'], quantity)
                elif self.position[product] < 0:
                    quantity = -1 * max(self.position[product], prices[product]['ask_volume'])
                    assert (quantity > 0), f"Quantity {quantity} not greater than 0 for {product} at {state.timestamp}"
                    prod_order = Order(product, prices[product]['ask'], quantity)                
                if product in results.keys():
                    results[product].append(prod_order)
                else:
                    results[product] = [prod_order]    



