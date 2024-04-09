import jsonpickle
import numpy as np
import pandas as pd
from datamodel import TradingState, Order
from typing import List

class Trader:
    def __init__(self):
        self.am_std_multiplier = 1.8
        self.am_window_size = 34
        self.am_position_open = False
        self.am_position_type = None
        self.am_historical_bid_prices = []
        self.am_historical_ask_prices = []
        self.am_remaining_quantity = 0
        self.am_open_order_volume = 0
        self.am_partially_closed = False
        self.am_latest_price = 0

    def run(self, state: TradingState):
        if state.traderData:
            saved_state = jsonpickle.decode(state.traderData)
            self.am_position_open = saved_state.am_position_open
            self.am_position_type = saved_state.am_position_type
            self.am_remaining_quantity = saved_state.am_remaining_quantity
            self.am_historical_bid_prices = saved_state.am_historical_bid_prices
            self.am_historical_ask_prices = saved_state.am_historical_ask_prices
            self.am_open_order_volume = saved_state.am_open_order_volume
            self.am_partially_closed = saved_state.am_partially_closed
            self.am_latest_price = saved_state.am_latest_price

        print('POSITION: ', state.position.get('AMETHYSTS', 0))

        result = {}
        conversions = 1

        if 'AMETHYSTS' in state.order_depths:
            am_order_depth = state.order_depths['AMETHYSTS']
            am_orders = []

            if am_order_depth.buy_orders and am_order_depth.sell_orders:
                am_bid_price = max(am_order_depth.buy_orders)
                self.am_historical_bid_prices.append(am_bid_price)
                am_ask_price = min(am_order_depth.sell_orders)
                self.am_historical_ask_prices.append(am_ask_price)

            if len(self.am_historical_bid_prices) > 34:
                am_bid_rolling_mean = pd.Series(self.am_historical_bid_prices).rolling(window=self.am_window_size).mean()
                am_bid_rolling_std = pd.Series(self.am_historical_bid_prices).rolling(window=self.am_window_size).std()
                am_upper_band = am_bid_rolling_mean + am_bid_rolling_std.values * self.am_std_multiplier

                am_ask_rolling_mean = pd.Series(self.am_historical_ask_prices).rolling(window=self.am_window_size).mean()
                am_ask_rolling_std = pd.Series(self.am_historical_ask_prices).rolling(window=self.am_window_size).std()
                am_lower_band = am_ask_rolling_mean - am_ask_rolling_std.values * 1.6

                am_latest_upper_band = am_upper_band.iloc[-1]
                print(am_latest_upper_band)
                am_latest_lower_band = am_lower_band.iloc[-1]
                print(am_latest_lower_band)

                am_live_ask_price, am_live_ask_volume = list(am_order_depth.sell_orders.items())[0]
                am_live_bid_price, am_live_bid_volume = list(am_order_depth.buy_orders.items())[0]

                print(self.am_position_open)
                print(self.am_remaining_quantity)
                print(self.am_open_order_volume)

                if not self.am_position_open:
                    if am_live_bid_price > am_latest_upper_band:
                        self.am_open_order_volume = min(abs(am_live_bid_volume), 10)
                        am_orders.append(Order('AMETHYSTS', am_live_bid_price, -self.am_open_order_volume))
                        print("am open upper")
                        self.am_latest_price = am_live_bid_price
                        self.am_position_open = True
                        self.am_position_type = 'Short'
                        self.am_remaining_quantity = self.am_open_order_volume

                        if self.am_open_order_volume < 20:
                            open_order_quant_2 = 20 - self.am_open_order_volume
                            am_orders.append(Order('AMETHYSTS', (am_live_bid_price + 1), -open_order_quant_2))
                            print("am open upper 2")
                            
                    elif am_live_ask_price < am_latest_lower_band:
                        self.am_open_order_volume = min(abs(am_live_ask_volume), 10)
                        am_orders.append(Order('AMETHYSTS', am_live_ask_price, self.am_open_order_volume))
                        print("am open lower")
                        self.am_latest_price = am_live_ask_price
                        self.am_position_open = True
                        self.am_position_type = 'Long'
                        self.am_remaining_quantity = self.am_open_order_volume

                        if self.am_open_order_volume < 20:
                            open_order_quant_2 = 20 - self.am_open_order_volume
                            am_orders.append(Order('AMETHYSTS', (am_live_ask_price - 1), open_order_quant_2))
                            print("am open lower 2")
                        
                elif self.am_position_open:
                    if not self.am_partially_closed:
                        if self.am_position_type == 'Long' and am_live_ask_price < am_latest_lower_band:
                            am_additional_volume = min(abs(20-self.am_open_order_volume), abs(am_live_ask_volume))
                            am_orders.append(Order('AMETHYSTS', am_live_ask_price, am_additional_volume))
                            self.am_remaining_quantity += am_additional_volume
                            print("additional long position")
                            self.am_position_open = True
                            self.am_position_type = 'Long'
                        elif self.am_position_type == 'Short' and am_live_bid_price > am_latest_upper_band:
                            am_additional_volume = min(abs(20-self.am_open_order_volume), abs(am_live_bid_volume))
                            am_orders.append(Order('AMETHYSTS', am_live_bid_price, -am_additional_volume))
                            self.am_remaining_quantity += am_additional_volume
                            print("additional short position")
                            self.am_position_open = True
                            self.am_position_type = 'Short'
                        if self.am_position_type == 'Short' and (am_live_ask_price < am_latest_lower_band or am_live_ask_price < self.am_latest_price):
                            am_closing_volume = min(abs(self.am_open_order_volume), abs(am_live_ask_volume))
                            am_orders.append(Order('AMETHYSTS', am_live_ask_price, am_closing_volume))
                            self.am_remaining_quantity -= am_closing_volume
                            if self.am_remaining_quantity > 0:
                                print("am partial close upper")
                                self.am_partially_closed = True
                                self.am_position_open = True
                                self.am_position_type = 'Short'
                            else:
                                print("am full close upper")
                                self.am_position_open = False
                                self.am_partially_closed = False
                        elif self.am_position_type == 'Long' and (am_live_bid_price > am_latest_upper_band or am_live_bid_price > self.am_latest_price):
                            am_closing_volume = min(abs(self.am_open_order_volume), abs(am_live_bid_volume))
                            am_orders.append(Order('AMETHYSTS', am_live_bid_price, -am_closing_volume))
                            self.am_remaining_quantity -= am_closing_volume
                            if self.am_remaining_quantity > 0:
                                print("am partial close lower")
                                self.am_partially_closed = True
                                self.am_position_open = True
                                self.am_position_type = 'Long'
                            else:
                                print("am full close lower")
                                self.am_partially_closed = False
                                self.am_position_open = False
                    elif self.am_partially_closed:
                        if self.am_position_type == 'Short' and (am_live_ask_price < am_latest_lower_band or am_live_ask_price < self.am_latest_price):
                            am_order_quantity = min(abs(self.am_remaining_quantity), abs(am_live_ask_volume))
                            am_orders.append(Order('AMETHYSTS', am_live_ask_price, am_order_quantity))
                            self.am_remaining_quantity -= am_order_quantity
                            if self.am_remaining_quantity > 0:
                                self.am_partially_closed = True
                                self.am_position_open = True
                                self.am_position_type = 'Short'
                            else:
                                self.am_partially_closed = False
                                self.am_position_open = False
                        elif self.am_position_type == 'Long' and (am_live_bid_price > am_latest_upper_band or am_live_bid_price > self.am_latest_price):
                            am_order_quantity = min(abs(self.am_remaining_quantity), abs(am_live_bid_volume))
                            am_orders.append(Order('AMETHYSTS', am_live_bid_price, -am_order_quantity))
                            self.am_remaining_quantity -= am_order_quantity
                            if self.am_remaining_quantity > 0:
                                self.am_partially_closed = True
                                self.am_position_open = True
                                self.am_position_type = 'Long'
                            else:
                                self.am_partially_closed = False
                                self.am_position_open = False
            
            traderData = jsonpickle.encode(self)
            result['AMETHYSTS'] = am_orders
            
        return result, conversions, traderData