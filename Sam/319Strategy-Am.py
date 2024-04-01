import jsonpickle
import numpy as np
import pandas as pd
from datamodel import TradingState, Order
from typing import List

class Trader:
    def __init__(self):
        self.position_open = False
        self.position_type = None
        self.std_multiplier = 0.3
        self.window_size = 20
        self.historical_prices = []
        self.remaining_quantity = 0
        self.open_order_volume = 0
        self.partially_closed = False

    def run(self, state: TradingState):
        if state.traderData:
            saved_state = jsonpickle.decode(state.traderData)
            self.position_open = saved_state.position_open
            self.position_type = saved_state.position_type
            self.remaining_quantity = saved_state.remaining_quantity
            self.historical_prices = saved_state.historical_prices
            self.open_order_volume = saved_state.open_order_volume
            self.partially_closed = saved_state.partially_closed

        print(len(self.historical_prices))
        print('open' if self.position_open else 'closed')

        result = {}
        conversions = 1

        if 'AMETHYSTS' in state.order_depths:
            order_depth = state.order_depths['AMETHYSTS']
            orders = []

            # Calculate current mid-price and append to historical prices
            if order_depth.buy_orders and order_depth.sell_orders:
                best_bid_price = max(order_depth.buy_orders)
                best_ask_price = min(order_depth.sell_orders)
                mid_price = (best_bid_price + best_ask_price) / 2
                print('mid price', mid_price)
                self.historical_prices.append(mid_price)

            # Perform linear regression if we have enough data
            if len(self.historical_prices) > 20:
                X = np.array(range(len(self.historical_prices)))
                y = np.array(self.historical_prices)
                m, b = self.linear_regression(X, y)
                predicted_prices = np.array([m * x + b for x in X])

                rolling_std = pd.Series(self.historical_prices).rolling(window=self.window_size).std()

                if rolling_std.isna().any():
                    rolling_std.fillna(method='bfill', inplace=True)
            
                upper_band = predicted_prices + rolling_std.values * self.std_multiplier
                lower_band = predicted_prices - rolling_std.values * self.std_multiplier

                latest_predicted_price = predicted_prices[-1]
                print(latest_predicted_price)
                latest_upper_band = upper_band[-1]
                print(latest_upper_band)
                latest_lower_band = lower_band[-1]
                print(latest_lower_band)

                # best_ask_price, best_ask_volume = min(order_depth.sell_orders.items(), key=lambda x: x[0])
                best_ask_price, best_ask_volume = list(order_depth.sell_orders.items())[0]
                # best_bid_price, best_bid_volume = max(order_depth.buy_orders.items(), key=lambda x: x[0])
                best_bid_price, best_bid_volume = list(order_depth.buy_orders.items())[0]

                print(self.position_open)
                print(self.remaining_quantity)
                print(self.open_order_volume)

                if not self.position_open:
                    if mid_price > latest_predicted_price:
                        self.open_order_volume = min(abs(best_bid_volume), 9)
                        orders.append(Order('AMETHYSTS', best_bid_price, -self.open_order_volume))
                        print("open upper")
                        self.position_open = True
                        self.position_type = 'Short'
                        self.remaining_quantity = self.open_order_volume
                    elif mid_price < latest_predicted_price:
                        self.open_order_volume = min(abs(best_ask_volume), 9)
                        orders.append(Order('AMETHYSTS', best_ask_price, self.open_order_volume))
                        print("open lower")
                        self.position_open = True
                        self.position_type = 'Long'
                        self.remaining_quantity = self.open_order_volume
                        
                elif self.position_open:
                    if not self.partially_closed:
                        if self.position_type == 'Short' and mid_price < latest_predicted_price:
                            closing_volume = min(abs(self.open_order_volume), abs(best_ask_volume))
                            print(closing_volume)
                            orders.append(Order('AMETHYSTS', best_ask_price, closing_volume))
                            self.remaining_quantity -= closing_volume
                            if self.remaining_quantity > 0:
                                print("partial close upper")
                                self.partially_closed = True
                                self.position_open = True
                                self.position_type = 'Short'
                            else:
                                print("full close upper")
                                self.partially_closed = False
                                self.position_open = False
                        elif self.position_type == 'Long' and mid_price > latest_predicted_price:
                            closing_volume = min(abs(self.open_order_volume), abs(best_bid_volume))
                            print(closing_volume)
                            orders.append(Order('AMETHYSTS', best_bid_price, -closing_volume))
                            self.remaining_quantity -= closing_volume
                            if self.remaining_quantity > 0:
                                print("partial close lower")
                                self.partially_closed = True
                                self.position_open = True
                                self.position_type = 'Long'
                            else:
                                print("full close lower")
                                self.partially_closed = False
                                self.position_open = False
                    elif self.partially_closed:
                        if self.position_type == 'Short' and mid_price < latest_predicted_price:
                            order_quantity = min(abs(self.remaining_quantity), abs(best_ask_volume))
                            print(order_quantity)
                            orders.append(Order('AMETHYSTS', best_ask_price, order_quantity))
                            self.remaining_quantity -= order_quantity
                            if self.remaining_quantity > 0:
                                self.partially_closed = True
                                self.position_open = True
                                self.position_type = 'Short'
                            else:
                                self.partially_closed = False
                                self.position_open = False
                        elif self.position_type == 'Long' and mid_price > latest_predicted_price:
                            order_quantity = min(abs(self.remaining_quantity), abs(best_bid_volume))
                            print(order_quantity)
                            orders.append(Order('AMETHYSTS', best_bid_price, -order_quantity))
                            self.remaining_quantity -= order_quantity
                            if self.remaining_quantity > 0:
                                self.partially_closed = True
                                self.position_open = True
                                self.position_type = 'Long'
                            else:
                                self.partially_closed = False
                                self.position_open = False
            
            traderData = jsonpickle.encode(self)
            result['AMETHYSTS'] = orders
            
        return result, conversions, traderData

    def linear_regression(self, X, y):
        X_mean = np.mean(X)
        y_mean = np.mean(y)
        m = np.sum((X - X_mean) * (y - y_mean)) / np.sum((X - X_mean)**2)
        b = y_mean - m * X_mean
        return m, b