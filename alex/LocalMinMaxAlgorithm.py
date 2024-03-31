from typing import List, Optional
import numpy as np
import pandas as pd
import jsonpickle
from collections import defaultdict
from datamodel import OrderDepth, UserId, TradingState, Order

# 

NHBD = 40
MIN_DATA_LENGTH = 3
TIMESTAMP_DELTA = 100

class Trader:

    def __init__(self):
        self.windows = {}
        self.positions = {}
        self.position_types = {}
        self.historical_prices = defaultdict(list)
     
    def prepare_data(self, data: pd.DataFrame, time_col: str, target_col: str) -> pd.DataFrame:
        """
        Prepare the data for regression analysis by calculating residuals.

        Args:
            data (pd.DataFrame): The input data containing the time, target, and predicted columns.
            time_col (str): The name of the column representing the time.
            target_col (str): The name of the column representing the target variable.
            y_pred_col (str): The name of the column representing the predicted values.

        Returns:
            pd.DataFrame: A DataFrame containing the time, target, and residuals columns.
        """

        X_train = data[time_col]
        y_train = data[target_col]
        newregressionData = {
            'timestamp': X_train,
            'mid_price': y_train
        }

        if len(X_train) < MIN_DATA_LENGTH:
            print("Not enough data to perform regression")
            return None

        m, c = np.polyfit(X_train, y_train, 1)
        regression_data = pd.DataFrame(newregressionData)
        regression_data['y_pred'] = m * X_train + c

        residuals = regression_data[target_col] - regression_data['y_pred']
        residuals_df = pd.DataFrame({time_col: regression_data[time_col], target_col: regression_data[target_col], 'residuals': residuals})

        return residuals_df
   
    def run(self, state: TradingState):

        # Deserialize traderData to get the trader state
        if state.traderData:
            saved_state = jsonpickle.decode(state.traderData)
            self.windows = saved_state.windows
            self.positions = saved_state.positions
            self.position_types = saved_state.position_types
            self.historical_prices = saved_state.historical_prices

        #---------------------TRADE STRATEGY---------------------------------------
        # Orders to be placed on exchange matching engine
        result = {}
        conversions = 1
        
        # Iterate through each product in the market
        for product, order_depth in state.order_depths.items():

            window = self.windows.get(product, None)
            position_open = self.positions.get(product, False)
            position_type = self.position_types.get(product, None)


            orders = []
            
            if order_depth.buy_orders and order_depth.sell_orders:
                best_bid_price = max(order_depth.buy_orders)
                best_ask_price = min(order_depth.sell_orders)
                mid_price = (best_bid_price + best_ask_price) / 2   # Calculate the mid price
                self.historical_prices[product].append(mid_price)
            
            # Skip the product if we don't have enough historical data
            if state.timestamp < (NHBD * TIMESTAMP_DELTA):
                continue
            
            # Create a DataFrame containing the mid prices and timestamps for the last NHBD data points
            mid_prices = self.historical_prices[product][-NHBD:] if len(self.historical_prices[product]) >= NHBD else self.historical_prices[product]
            times = range((state.timestamp - (NHBD * TIMESTAMP_DELTA)), (state.timestamp), TIMESTAMP_DELTA)
            new_product_df = {
                'mid_price': mid_prices,
                'timestamp': times    
            }
            product_df = pd.DataFrame(new_product_df)  
                             
            # Prepare the data for regression analysis by calculating residuals
            residuals_df = self.prepare_data(product_df, 'timestamp', 'mid_price')
            if residuals_df is None:
                continue

            # Calculate the signs of the residuals at current_time and prev_time
            current_residual_sign = np.sign(residuals_df['residuals'].iloc[-1])
            prev_residual_sign = np.sign(residuals_df['residuals'].iloc[-2]) if len(residuals_df) > 1 else 0

            #---------------------OPEN/CLOSE POSITIONS---------------------------------------

            # First Layer: Open tracking windows and determine position type
            if window is None and not position_open and current_residual_sign < prev_residual_sign:
                window = residuals_df.iloc[-1:] # Start a new window
                position_type = 'long'
            
            elif window is None and not position_open and current_residual_sign > prev_residual_sign:
                window = residuals_df.iloc[-1:] # Start a new window
                position_type = 'short'
            
            # Update the window if it already exists
            elif window is not None:
                window = residuals_df.iloc[((-1 * len(window)) - 1):]
                mean_rate_of_change = (window['residuals'].diff() / window['timestamp'].diff()).mean()

                # Second layer: Open/Close positions
                #Open positions
                if not position_open:
                    if mean_rate_of_change >= 0 and position_type == 'long':
                        orders.append(Order(product, best_ask_price, -1))  # Open long position
                        position_open = True
                    
                    elif mean_rate_of_change <= 0 and position_type == 'short':
                        orders.append(Order(product, best_bid_price, -1))   # Open short position
                        position_open = True
                
                # Close positions
                elif position_open:
                    close_position_condition = residuals_df['residuals'].iloc[-1]
                    if close_position_condition > 0 and position_type == 'long':
                        orders.append(Order(product, best_bid_price, 1))   # Close long position
                        window = None
                        position_open = False
                        position_type = None

                    elif close_position_condition < 0 and position_type == 'short':
                        orders.append(Order(product, best_ask_price, 1))    # Close short position
                        window = None
                        position_open = False
                        position_type = None
            
            # Save the trader state for the product next iteration of run()
            self.windows[product] = window
            self.positions[product] = position_open
            self.position_types[product] = position_type

            # Add the orders for product to the result dictionary
            result[product] = orders
            print("Orders for product", product, ":", orders)

        # Serialize the trader state to be saved for the next iteration
        traderData = jsonpickle.encode(self)

        return result, conversions, traderData
