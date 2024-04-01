import jsonpickle
import numpy as np
import pandas as pd
from datamodel import TradingState, Order

class Trader:
    def __init__(self):
        self.position_open = False
        self.position_type = None
        self.std_multiplier = 2
        self.window_size = 20
        self.historical_prices = []

    def run(self, state: TradingState):
        # Deserialize traderData to get the trader state
        if state.traderData:
            saved_state = jsonpickle.decode(state.traderData)
            self.position_open = saved_state.position_open
            self.position_type = saved_state.position_type
            self.historical_prices = saved_state.historical_prices

        print(len(self.historical_prices))
        print('open' if self.position_open else 'closed')

        result = {}
        conversions = 1

        if 'STARFRUIT' in state.order_depths:
            order_depth = state.order_depths['STARFRUIT']
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

                best_ask_price, best_ask_volume = min(order_depth.sell_orders.items(), key=lambda x: x[0])
                print(best_ask_price)
                print(best_ask_volume)
                best_bid_price, best_bid_volume = max(order_depth.buy_orders.items(), key=lambda x: x[0])
                print(best_bid_price)
                print(best_bid_volume)

                if not self.position_open:
                    if mid_price > latest_upper_band:
                        orders.append(Order('STARFRUIT', best_bid_price, -1))  # Open short position
                        self.position_open = True
                        self.position_type = 'Short'
                        print('open upper')
                    elif mid_price < latest_lower_band:
                        orders.append(Order('STARFRUIT', best_ask_price, -1))  # Open long position
                        self.position_open = True
                        self.position_type = 'Long'
                        print('open lower')
                elif self.position_open:
                    if self.position_type == 'Short' and mid_price < latest_predicted_price:
                        orders.append(Order('STARFRUIT', best_ask_price, -1))  # Close short position
                        self.position_open = False
                        print('close upper')
                    elif self.position_type == 'Long' and mid_price > latest_predicted_price:
                        orders.append(Order('STARFRUIT', best_bid_price, -1))  # Close long position
                        self.position_open = False
                        print('close lower')

            traderData = jsonpickle.encode(self)
            result['STARFRUIT'] = orders

        return result, conversions, traderData

    def linear_regression(self, X, y):
        X_mean = np.mean(X)
        y_mean = np.mean(y)
        m = np.sum((X - X_mean) * (y - y_mean)) / np.sum((X - X_mean)**2)
        b = y_mean - m * X_mean
        return m, b