from typing import Dict, List
from datamodel import OrderDepth, TradingState, Order
import collections
from collections import defaultdict
import random
import math
import copy
import numpy as np
import jsonpickle
import pandas as pd
import collections


# Author: Rick Howell, Alex Morrow
# University of Miami, 2024

class Trader:
    def __init__ (self):
        self.position = copy.deepcopy({'STARFRUIT': 0, 'AMETHYSTS': 0, 'ORCHIDS': 0})
        self.orchid_data_dict = {'timestamp': [], 'sunlight': [], 'humidity': [], 'price': []}
        self.counter = 0
        self.predictions = []
        self.c_orchids = 0

    def update_fees(self, state: TradingState):
        """
        Update the fees incurred by the trader.

        Parameters:
        - state (TradingState): The current state of the market.

        """
        

        
    def rolling_linear_regression_with_reg(self, target_col: str, lambda_reg=0.01, num_rows=10) -> List[float]:
        """
        Perform rolling linear regression with regularization.

        Args:
            target_col (str): The target column for regression.
            lambda_reg (float, optional): Regularization parameter. Defaults to 0.01.
            num_rows (int, optional): Number of rows to consider in each rolling window. Defaults to 10.

        Returns:
            List[float]: List of predicted values for the target column.
        """
        data = self.orchid_data_dict[target_col]  # Extract data list for the target column

        if len(data) < num_rows:
            return [np.nan] * num_rows

        # Prepare X matrix using ones and the target column data
        X = np.vstack([np.ones(num_rows), data[-num_rows:]]).T
        y = data[-num_rows:]  # Shifted target values for regression

        # Regularization matrix
        reg = lambda_reg * np.eye(X.shape[1])
        # Calculating beta (coefficients) using regularized linear regression
        beta = np.linalg.inv(X.T @ X + reg) @ X.T @ y

        predictions = []
        # Prediction for the next data point
        for j in range(len(data) - num_rows, len(data)):
            next_input = np.array([1, data[j-1]])
            prediction = next_input @ beta
            predictions.append(prediction)

        return predictions

    def calc_next_price_observations(self, sunlight, humidity, mid_price):
        """
        Calculates the predicted price of an orchid based on the given sunlight, humidity, and mid_price.

        Parameters:
        sunlight (float): The amount of sunlight in hours per day.
        humidity (float): The humidity level.
        mid_price (float): The current mid price of the orchid.

        Returns:
        float: The predicted price of the orchid.

        """
        sunlight_hrs_per_day = 10000/24
        sunlight_ten_mins = sunlight_hrs_per_day/6
        sunlight_minus = 0.04/sunlight_ten_mins

        humidity_impact = max(0, (0.04*(abs(humidity-70) - 10)))
        predicted_price = mid_price - humidity_impact

        if sunlight / sunlight_hrs_per_day < 7:
            predicted_price -= (sunlight_minus * mid_price)
        
        return predicted_price
    
    def calc_nth_price_observations(self, n, mid_price):
        """
        Calculate the nth price observations based on the given inputs.

        Parameters:
        - n (int): The number of observations to calculate.
        - mid_price (float): The initial mid price.

        Returns:
        - predictions (list): List of predicted prices.

        """
        humidity = self.rolling_linear_regression_with_reg('humidity', 0.01, n)
        sunlight = self.rolling_linear_regression_with_reg('sunlight', 0.01, n)

        if math.isnan(humidity[-1]):
            return []

        predictions = []
        for i in range(len(sunlight) - n ,len(sunlight)):
            next_price = self.calc_next_price_observations(sunlight[i], humidity[i], mid_price)
            mid_price = next_price
            predictions.append(next_price)
        
        return predictions

    def run(self, state: TradingState):
        INF = int(1e9)
        conversions = 1
        result = {}
        WINDOW_SIZE = 100


        if state.traderData:
            saved_state = jsonpickle.decode(state.traderData)
            self.orchid_data_dict = saved_state.orchid_data_dict
            self.position = saved_state.position
            self.predictions = saved_state.predictions

        for product in self.position:
            self.position[product] = state.position.get(product, 0)

        print(f"POSITION: {self.position['ORCHIDS']}")

        if self.position['ORCHIDS'] < 0 or self.position['ORCHIDS'] > 0:
            conversions = -self.position['ORCHIDS']


        # Get the best buy and sell prices
        orchid_best_sell = min(state.order_depths['ORCHIDS'].sell_orders.keys())
        orchid_best_sell_volume = state.order_depths['ORCHIDS'].sell_orders[orchid_best_sell]
        orchid_best_buy = max(state.order_depths['ORCHIDS'].buy_orders.keys())
        orchid_best_buy_volume = state.order_depths['ORCHIDS'].buy_orders[orchid_best_buy]
        mp = (orchid_best_sell + orchid_best_buy) / 2

        orchid_obs = state.observations.conversionObservations.get('ORCHIDS', None)
        sunlight = orchid_obs.sunlight
        humidity = orchid_obs.humidity

        exports = orchid_obs.exportTariff
        imports = orchid_obs.importTariff
        transFees = orchid_obs.transportFees

        # Update the Orchid data dictionary
        self.orchid_data_dict['timestamp'].append(state.timestamp)
        self.orchid_data_dict['sunlight'].append(sunlight)
        self.orchid_data_dict['humidity'].append(humidity)
        self.orchid_data_dict['price'].append(mp)
        if (state.timestamp / 100) % WINDOW_SIZE == 0:
            orchids_orders = []
            self.predictions = self.calc_nth_price_observations(WINDOW_SIZE, mp)

            if len(self.predictions) != 0:
                print(f"Predictions: {self.predictions}")
                mean_roc = np.mean(np.diff(self.predictions))
                print(f"Mean Rate of Change: {mean_roc}")
                if mean_roc < 0:
                    orchids_orders.append(Order('ORCHIDS', orchid_best_buy, -orchid_best_buy_volume))
                    print(f"SELLING ORCHIDS: {orchid_best_buy} at {orchid_best_buy_volume}")
                    self.c_orchids += -orchid_best_buy_volume
                elif abs(self.c_orchids) >= 1000:
                    orchids_orders.append(Order('ORCHIDS', orchid_best_sell, orchid_best_sell_volume))
                    print(f"BUYING ORCHIDS: {orchid_best_sell} at {orchid_best_sell_volume}")
                    self.c_orchids += orchid_best_sell_volume
                
                result['ORCHIDS'] = orchids_orders      
        else:
            print("No predictions made.")
        return result, conversions, jsonpickle.encode(self)
