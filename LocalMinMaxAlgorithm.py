from typing import List, Optional
import numpy as np
import pandas as pd
import string
import jsonpickle
from collections import defaultdict
from datamodel import OrderDepth, UserId, TradingState, Order

NHBD = 10
MIN_DATA_LENGTH = 3

class Trader:

    def __init__(self):
        self.window = None
        self.position_open = False
        self.position_type = None
        self.historical_prices = defaultdict(list)
    
    def train_linear_regression_model(self, time_col: str, target_col: str, data: pd.DataFrame) -> Optional[pd.DataFrame]:
        """
        Trains a linear regression model using the provided data.

        Args:
            time_col (str): The name of the column containing the time values.
            target_col (str): The name of the column containing the target values.
            data (pd.DataFrame): The input data containing the time and target columns.

        Returns:
            pd.DataFrame: A DataFrame containing the input data along with the predicted values.
                         Returns None if the length of the input data is less than MIN_DATA_LENGTH.
        """
        X_train = data[time_col]
        y_train = data[target_col]
        newregressionData = {
            'timestamp': X_train,
            'mid_price': y_train
        }
        
        if len(X_train) < MIN_DATA_LENGTH:
            return None
        
        m, c = np.polyfit(X_train, y_train, 1)
        regression_data = pd.DataFrame(newregressionData)
        regression_data['y_pred'] = m * X_train + c
        
        return regression_data
    
   
    def run(self, state: TradingState):
        """
        Executes the trading strategy based on the current state.

        Args:
            state (TradingState): The current trading state.

        Returns:
            tuple: A tuple containing the following:
                - dict: A dictionary of orders to be placed on the exchange matching engine.
                - int: The number of conversions.
                - str: The serialized trader state to be saved for the next iteration.
        """

        # Deserialize traderData to get the trader state
        if state.traderData:
            saved_state = jsonpickle.decode(state.traderData)
            self.window = saved_state.window
            self.position_open = saved_state.position_open
            self.position_type = saved_state.position_type
            self.historical_prices = saved_state.historical_prices

        #---------------------TRADE STRATEGY---------------------------------------
        # Orders to be placed on exchange matching engine
        result = {}
        conversions = 1
        
        # Iterate through each product in the market
        for product, order_depth in state.order_depths.items():

            orders = []
            
            if order_depth.buy_orders and order_depth.sell_orders:
                best_bid_price = max(order_depth.buy_orders)
                best_ask_price = min(order_depth.sell_orders)
                mid_price = (best_bid_price + best_ask_price) / 2   # Calculate the mid price
                self.historical_prices[product].append(mid_price)
            
            # Skip the product if we don't have enough historical data
            if state.timestamp < (NHBD * 100):
                continue
            
            # Create a DataFrame containing the mid prices and timestamps for the last NHBD data points
            mid_prices = self.historical_prices[product][-NHBD:] if len(self.historical_prices[product]) >= NHBD else self.historical_prices[product]
            times = range((state.timestamp - (NHBD * 100)), (state.timestamp), 100)
            new_product_df = {
                'mid_price': mid_prices,
                'timestamp': times    
            }
            product_df = pd.DataFrame(new_product_df)  
                             
            # Perform linear regression if we have enough data       
            regression_data = self.train_linear_regression_model('timestamp', 'mid_price', product_df)
            if regression_data is None:
                print("Not enough data to perform regression at time " + str(state.timestamp))
                break
            
            # Calculate the residuals
            residuals = regression_data['mid_price'] - regression_data['y_pred']
            residuals_df = pd.DataFrame({'timestamp': regression_data['timestamp'], 'mid_price': regression_data['mid_price'], 'residuals': residuals})

            # Calculate the signs of the residuals at current_time and prev_time
            current_residual_sign = np.sign(residuals_df['residuals'].iloc[-1])
            prev_residual_sign = np.sign(residuals_df['residuals'].iloc[-2]) if len(residuals_df) > 1 else 0

            #---------------------OPEN/CLOSE POSITIONS---------------------------------------

            # Check if the residuals have crossed zero from pos to neg and no tracking window is currently open
            if self.window is None and current_residual_sign < prev_residual_sign:
                self.window = residuals_df.iloc[-1:] # Start a new window
                self.position_type = 'long'
            
            elif self.window is not None and self.position_type == 'long':
                self.window = residuals_df.iloc[((-1 * len(self.window)) - 1):]
                mean_rate_of_change = (self.window['residuals'].diff() / self.window['timestamp'].diff()).mean()
                if not self.position_open:
                    print(mean_rate_of_change)

                # Check if there is no open position and the mean rate of change is positive
                if not self.position_open and mean_rate_of_change >= 0:
                    orders.append(Order(product, best_ask_price, -1))   # Open long position
                    self.position_open = True
                    self.window = None
                
                # Check if there is an open position and the current residual is positive
                elif self.position_open and residuals_df['residuals'].iloc[-1] >= 0:
                    orders.append(Order(product, best_bid_price, 1))    # Close long position
                    self.position_open = False
                    self.position_type = None

            # Check if there is no window and the residuals cross from neg to pos
            elif self.window is not None and current_residual_sign > prev_residual_sign:
                self.window = residuals_df.iloc[-1:] # Start a new window
                self.position_type = 'short'
            
            # Check if there is a window
            elif self.window is not None and self.position_type == 'short':
                self.window = residuals_df.iloc[((-1 * len(self.window)) - 1):]
                mean_rate_of_change = (self.window['residuals'].diff() / self.window['timestamp'].diff()).mean()
                if not self.position_open:
                    print(mean_rate_of_change)

                # Check if there is no open position and the mean rate of change is negative
                if not self.position_open and mean_rate_of_change <= 0:
                    orders.append(Order(product, best_bid_price, -1))   # Open short position
                    self.position_open = True
                    self.window = None
                         
                # Check if there is an open position and the current residual is negative
                elif self.position_open and residuals_df['residuals'].iloc[-1] <= 0:
                    orders.append(Order(product, best_ask_price, 1))    # Close short position
                    self.position_open = False
                    self.position_type = None

            # Add the orders for product to the result dictionary
            result[product] = orders
            print("Orders for product", product, ":", orders)

        # Serialize the trader state to be saved for the next iteration
        traderData = jsonpickle.encode(self)

        return result, conversions, traderData
