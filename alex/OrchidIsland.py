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
        self.orchid_data_dict = {'timestamp': [], 'sunlight': [], 'humidity': [], 'mid_price': [], 'island_ask': [], 'island_bid': [], 'island_mp': [], 'island_bid_predicted': [], 'island_ask_predicted': []}
        self.counter = 0
        self.predictions = []
        self.island_prices = []

        
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

        if humidity < 60:
            humidity_impact = ((60 - humidity) // 5) * 0.02
        elif humidity > 80:
            humidity_impact = ((humidity - 80) // 5) * 0.02
        else:
            humidity_impact = 0

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
    
    def test_bid_ask_predictions(self):
        """
        Calculate the mean squared error between the actual and predicted prices.

        Parameters:
        - actual_prices (list): List of actual prices.
        - predicted_prices (list): List of predicted prices.

        Returns:
        - float: The mean squared error for bid prices.
        - float: The mean squared error for ask prices.
        """

        predicted_bid_prices = self.orchid_data_dict['island_bid_predicted'][1:]
        predicted_ask_prices = self.orchid_data_dict['island_ask_predicted'][1:]
        
        actual_bid_prices = self.orchid_data_dict['island_bid'][1:]
        actual_ask_prices = self.orchid_data_dict['island_ask'][1:]

        return np.mean((np.array(actual_bid_prices) - np.array(predicted_bid_prices))**2), np.mean((np.array(actual_ask_prices) - np.array(predicted_ask_prices))**2)

    def update_dict(self, state: TradingState):

        # Get the best buy and sell prices
        orchid_best_sell = min(state.order_depths['ORCHIDS'].sell_orders.keys())
        orchid_best_buy = max(state.order_depths['ORCHIDS'].buy_orders.keys())
        mp = (orchid_best_sell + orchid_best_buy) / 2

        # Extract Orchid observations
        orchid_obs = state.observations.conversionObservations.get('ORCHIDS', None)
        sunlight = orchid_obs.sunlight
        humidity = orchid_obs.humidity
        island_ask = orchid_obs.askPrice
        island_bid = orchid_obs.bidPrice
        island_mp = (island_ask + island_bid) / 2

        # Update the Orchid data dictionary
        self.orchid_data_dict['timestamp'].append(state.timestamp)
        self.orchid_data_dict['sunlight'].append(sunlight)
        self.orchid_data_dict['humidity'].append(humidity)
        self.orchid_data_dict['mid_price'].append(mp)
        self.orchid_data_dict['island_ask'].append(orchid_obs.askPrice)
        self.orchid_data_dict['island_bid'].append(orchid_obs.bidPrice)
        self.orchid_data_dict['island_mp'].append(island_mp)

    def run(self, state: TradingState):
        INF = int(1e9)
        conversions = 1
        result = {}
        WINDOW_SIZE = 10

        # Load saved state
        if state.traderData:
            saved_state = jsonpickle.decode(state.traderData)
            self.orchid_data_dict = saved_state.orchid_data_dict
            self.position = saved_state.position
            self.predictions = saved_state.predictions

        # Update positions
        for product in self.position:
            self.position[product] = state.position.get(product, 0)

        orchid_position = self.position['ORCHIDS']
        print(f"POSITION: {orchid_position}")
        self.update_dict(state) # Update the Orchid data dictionary
        obs = state.observations.conversionObservations.get('ORCHIDS', None)
        # To adjust Island conversions
        exports = obs.exportTariff
        imports = obs.importTariff
        trans_fee = obs.transportFees
        # Environmental Variables
        sunlight = obs.sunlight
        humidity = obs.humidity
        # Island Prices
        island_ask = obs.askPrice
        island_bid = obs.bidPrice

        if state.timestamp == 0:
            self.orchid_data_dict['island_bid_predicted'].append(np.nan)
            self.orchid_data_dict['island_ask_predicted'].append(np.nan)
            return result, conversions, jsonpickle.encode(self)
        
        if orchid_position != 0:
            conversions = -orchid_position
            print(f"CONVERTING POSITION TO ISLAND: {conversions}")

        self.orchid_data_dict['island_bid_predicted'].append(self.calc_next_price_observations(sunlight, humidity, island_bid))
        self.orchid_data_dict['island_ask_predicted'].append(self.calc_next_price_observations(sunlight, humidity, island_ask))

        predicted_bid = self.orchid_data_dict['island_bid_predicted'][-1]
        predicted_ask = self.orchid_data_dict['island_ask_predicted'][-1]

        pred_bid_adjusted = predicted_bid + exports + trans_fee
        pred_ask_adjusted = predicted_ask + imports + trans_fee

        order_depth = state.order_depths['ORCHIDS']
        osell = collections.OrderedDict(sorted(order_depth.sell_orders.items()))
        obuy = collections.OrderedDict(sorted(order_depth.buy_orders.items(), reverse=True))

        orders = []
        cur_position = prior_position = self.position['ORCHIDS']
        cum_buy_quant = prior_position
        for ask, vol in osell.items():
            print(f"ASK: {ask} <= PRED_BID: {pred_bid_adjusted}")
            if(ask <= pred_bid_adjusted) and cur_position < 100:
                quantity = min(abs(vol), (100 - cur_position), (100 - cum_buy_quant))
                cur_position += quantity
                cum_buy_quant += quantity
                assert(quantity >= 0)
                orders.append(Order('ORCHIDS', ask, quantity)) if cum_buy_quant <= 100 else None
                print(f"BUYING ORCHIDS: {ask} at {quantity}")

        cum_sell_quant = prior_position
        for bid, vol in obuy.items():
            print(f"BID: {bid} >= PRED_ASK: {pred_ask_adjusted}")
            if(bid >= pred_ask_adjusted) and cur_position > -100:
                quantity = max(-vol, (-100 - cur_position), (-100 - cum_sell_quant))
                cur_position += quantity
                cum_sell_quant += quantity
                assert(quantity <= 0)
                orders.append(Order('ORCHIDS', bid, quantity)) if cum_sell_quant >= -100 else None
                print(f"SELLING ORCHIDS: {bid} at {quantity}")

        return result, conversions, jsonpickle.encode(self)

