import jsonpickle
import numpy as np
import pandas as pd
from datamodel import TradingState, OrderDepth, Order

class Trader:
    def __init__(self):
        self.bid_prices_history = {}
        self.ask_prices_history = {}
        self.position_open = {}
        self.position_type = {}

    def calculate_moving_average(self, bid_prices, ask_prices, window):
        """
        Calculates the moving average of a given list of bid and ask prices.

        Args:
            bid_prices (list): A list of bid prices.
            ask_prices (list): A list of ask prices.
            window (int): The number of prices to consider in the moving average calculation.

        Returns:
            tuple: A tuple containing the moving average of the bid prices and the moving average of the ask prices.

        Raises:
            None

        """
        if len(bid_prices) < window:
            return None, None  # Not enough data to calculate
        return (sum(bid_prices[-window:]) / window), (sum(ask_prices[-window:]) / window)

    def calculate_order_book_imbalance(self, order_depth):
        """
        Calculates the order book imbalance based on the given order depth.

        Parameters:
        - order_depth: An object representing the order depth of the market.

        Returns:
        - imbalance: The calculated order book imbalance.

        The order book imbalance is calculated as the difference between the total buy volume and the total sell volume,
        divided by the total volume. If the total volume is zero, the imbalance is set to zero to prevent division by zero.
        """
        total_buy_volume = sum(amount for price, amount in order_depth.buy_orders.items())
        print("Total buy volume: ", total_buy_volume)
        total_sell_volume = sum(-amount for price, amount in order_depth.sell_orders.items())
        print("Total sell volume: ", total_sell_volume)
        total_volume = total_buy_volume + total_sell_volume
        if total_volume == 0:  # Prevent division by zero
            return 0
        imbalance = (total_buy_volume - total_sell_volume) / total_volume
        return imbalance

    def run(self, state : TradingState):

        SHORT_TERM_WINDOW = 5
        LONG_TERM_WINDOW = 25
        IMBALANCE_THRESHOLD = 0.9   # Threshold for order book imbalance

        # Deserialize traderData to get the trader state
        if state.traderData:
            saved_state = jsonpickle.decode(state.traderData)
            self.bid_prices_history = saved_state.bid_prices_history
            self.ask_prices_history = saved_state.ask_prices_history
            self.position_open = saved_state.position_open
            self.position_type = saved_state.position_type

        conversions = 1
        result = {}
        for product, order_depth in state.order_depths.items():
            # Initialize product history
            if product not in self.bid_prices_history:
                self.bid_prices_history[product] = []
                self.ask_prices_history[product] = []
                self.position_open[product] = False
                self.position_type[product] = None

            best_ask = min(order_depth.sell_orders)
            best_bid = max(order_depth.buy_orders)
            best_bid_amount = order_depth.buy_orders[best_bid]
            best_ask_amount = order_depth.sell_orders[best_ask]
            self.bid_prices_history[product].append(best_bid) # Use the best bid price for consistent signaling
            self.ask_prices_history[product].append(best_ask)

            bid_short_term_ma, ask_short_term_ma = self.calculate_moving_average(self.bid_prices_history[product], self.ask_prices_history[product], SHORT_TERM_WINDOW)
            bid_long_term_ma, ask_long_term_ma = self.calculate_moving_average(self.bid_prices_history[product], self.ask_prices_history[product], LONG_TERM_WINDOW)
            imbalance = self.calculate_order_book_imbalance(order_depth)

            orders = []
            if bid_short_term_ma and bid_long_term_ma:

                pType = self.position_type.get(product)
                if self.position_open[product]:

                    if pType == 'long' and bid_short_term_ma < bid_long_term_ma:
                        orders.append(Order(product, best_bid, -1)) # Close long position
                        self.position_open[product] = False
                        self.position_type[product] = None
                        print("Long position closed for product: ", product, " at price: ", best_bid)
                    elif pType == 'short' and ask_short_term_ma > ask_long_term_ma:
                        orders.append(Order(product, best_ask, 1))  # Close short position
                        self.position_open[product] = False
                        self.position_type[product] = None
                        print("Short position closed for product: ", product, " at price: ", best_ask)

                elif not self.position_open[product]:

                    if ask_short_term_ma > ask_long_term_ma and imbalance > IMBALANCE_THRESHOLD:  # Anticipate upward movement, long signal
                        orders.append(Order(product, best_ask, 1))
                        self.position_open[product] = True
                        self.position_type[product] = 'long'
                        print("Long signal detected for product: ", product, " at price: ", best_ask, " with imbalance: ", imbalance)
                    elif bid_short_term_ma < bid_long_term_ma and imbalance < -IMBALANCE_THRESHOLD:  # Anticipate downward movement, short signal
                        orders.append(Order(product, best_bid, -1))
                        self.position_open[product] = True
                        self.position_type[product] = 'short'
                        print("Short signal detected for product: ", product, " at price: ", best_bid, " with imbalance: ", imbalance)

            result[product] = orders
        
        # Serialize the trader state
        traderData = jsonpickle.encode(self)

        return result, conversions, traderData
