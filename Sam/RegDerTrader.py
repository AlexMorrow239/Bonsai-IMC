import json
import numpy as np
import pandas as pd
from datamodel import TradingState, Order

class Trader:
    def __init__(self):
        self.position_open = False
        self.position_type = None
        self.std_multiplier = 2
        self.window_size = 20

    def run(self, state: TradingState):
        result = {}
        conversions = 1

        # Deserialize traderData to get historical prices
        historical_prices = json.loads(state.traderData) if state.traderData else []

        if 'STARFRUIT' in state.order_depths:
            order_depth = state.order_depths['STARFRUIT']
            orders = []

            # Calculate current mid-price and append to historical prices
            if order_depth.buy_orders and order_depth.sell_orders:
                best_bid_price = max(order_depth.buy_orders)
                best_ask_price = min(order_depth.sell_orders)
                mid_price = (best_bid_price + best_ask_price) / 2
                historical_prices.append(mid_price)

            # Perform linear regression if we have enough data
            if len(historical_prices) > 1:
                X = np.array(range(len(historical_prices)))
                y = np.array(historical_prices)
                m, b = self.linear_regression(X, y)
                predicted_prices = np.array([m * x + b for x in X])
            
                # Ensure there's enough data for rolling calculation
                if len(historical_prices) >= self.window_size:
                    # Calculate rolling standard deviation
                    rolling_std = pd.Series(historical_prices).rolling(window=self.window_size).std(ddof=0)
                else:
                    # Use the full available data if window size is not met
                    rolling_std = pd.Series(historical_prices).rolling(window=len(historical_prices)).std(ddof=0)
            
                # Handling case where rolling_std may not be fully populated
                if rolling_std.isna().any():
                    rolling_std.fillna(method='bfill', inplace=True)  # Backfill any NaN values
            
                # Calculate Bollinger Bands
                upper_band = predicted_prices + rolling_std.values * self.std_multiplier
                lower_band = predicted_prices - rolling_std.values * self.std_multiplier

                # Latest data for decision making
                latest_predicted_price = predicted_prices[-1]
                latest_upper_band = upper_band[-1]
                latest_lower_band = lower_band[-1]

                # Trading logic
                best_ask_price, best_ask_volume = min(order_depth.sell_orders.items(), key=lambda x: x[0])
                best_bid_price, best_bid_volume = max(order_depth.buy_orders.items(), key=lambda x: x[0])

                print(latest_upper_band)
                print(latest_lower_band)
                print(latest_predicted_price)
                print(mid_price)

                if mid_price > latest_upper_band and not self.position_open:
                    # Open long position
                    orders.append(Order('STARFRUIT', best_bid_price, 1))
                    self.position_open = True
                    self.position_type = 'Long'

                elif mid_price < latest_lower_band and not self.position_open:
                    # Open short position
                    orders.append(Order('STARFRUIT', best_ask_price, -1))
                    self.position_open = True
                    self.position_type = 'Short'

                elif mid_price < latest_predicted_price and self.position_open and self.position_type == 'Long':
                    # Close long position
                    orders.append(Order('STARFRUIT', best_ask_price, -1))
                    self.position_open = False

                elif mid_price > latest_predicted_price and self.position_open and self.position_type == 'Short':
                    # Close short position
                    orders.append(Order('STARFRUIT', best_bid_price, 1))
                    self.position_open = False

            # Serialize historical prices and store in traderData
            traderData = json.dumps(historical_prices)

            result['STARFRUIT'] = orders

        return result, conversions, traderData

    def linear_regression(self, X, y):
        X_mean = np.mean(X)
        y_mean = np.mean(y)
        m = np.sum((X - X_mean) * (y - y_mean)) / np.sum((X - X_mean)**2)
        b = y_mean - m * X_mean
        return m, b