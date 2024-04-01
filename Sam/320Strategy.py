import jsonpickle
import numpy as np
import pandas as pd
from datamodel import TradingState, Order
from typing import List

class Trader:
    def __init__(self):
        self.position_open = False
        self.position_type = None
        self.std_multiplier = 2
        self.window_size = 20
        self.historical_bid_prices = []
        self.historical_ask_prices = []
        self.remaining_quantity = 0
        self.open_order_volume = 0
        self.partially_closed = False
        self.latest_price = 0

    def run(self, state: TradingState):
        if state.traderData:
            saved_state = jsonpickle.decode(state.traderData)
            self.position_open = saved_state.position_open
            self.position_type = saved_state.position_type
            self.remaining_quantity = saved_state.remaining_quantity
            self.historical_bid_prices = saved_state.historical_bid_prices
            self.historical_ask_prices = saved_state.historical_ask_prices
            self.open_order_volume = saved_state.open_order_volume
            self.partially_closed = saved_state.partially_closed
            self.latest_price = saved_state.latest_price

        print(len(self.historical_bid_prices))
        print(len(self.historical_ask_prices))
        print('open' if self.position_open else 'closed')

        result = {}
        conversions = 1

        if 'STARFRUIT' in state.order_depths:
            order_depth = state.order_depths['STARFRUIT']
            orders = []

            if order_depth.buy_orders and order_depth.sell_orders:
                bid_price = max(order_depth.buy_orders)
                self.historical_bid_prices.append(bid_price)
                ask_price = min(order_depth.sell_orders)
                self.historical_ask_prices.append(ask_price)

            if len(self.historical_bid_prices) > 20:
                bid_rolling_mean = pd.Series(self.historical_bid_prices).rolling(window=self.window_size).mean()
                bid_rolling_std = pd.Series(self.historical_bid_prices).rolling(window=self.window_size).std()
                upper_band = bid_rolling_mean + bid_rolling_std.values * self.std_multiplier

                ask_rolling_mean = pd.Series(self.historical_ask_prices).rolling(window=self.window_size).mean()
                ask_rolling_std = pd.Series(self.historical_ask_prices).rolling(window=self.window_size).std()
                lower_band = ask_rolling_mean - ask_rolling_std.values * self.std_multiplier

                latest_upper_band = upper_band.iloc[-1]
                print(latest_upper_band)
                latest_lower_band = lower_band.iloc[-1]
                print(latest_lower_band)

                live_ask_price, live_ask_volume = list(order_depth.sell_orders.items())[0]
                live_bid_price, live_bid_volume = list(order_depth.buy_orders.items())[0]

                print(self.position_open)
                print(self.remaining_quantity)
                print(self.open_order_volume)

                if not self.position_open:
                    if live_bid_price > latest_upper_band:
                        self.open_order_volume = min(abs(live_bid_volume), 20)
                        orders.append(Order('STARFRUIT', live_bid_price, -self.open_order_volume))
                        print("open upper")
                        self.latest_price = live_bid_price
                        self.position_open = True
                        self.position_type = 'Short'
                        self.remaining_quantity = self.open_order_volume
                    elif live_ask_price < latest_lower_band:
                        self.open_order_volume = min(abs(live_ask_volume), 20)
                        orders.append(Order('STARFRUIT', live_ask_price, self.open_order_volume))
                        print("open lower")
                        self.latest_price = live_ask_price
                        self.position_open = True
                        self.position_type = 'Long'
                        self.remaining_quantity = self.open_order_volume
                        
                elif self.position_open:
                    if not self.partially_closed:
                        if self.position_type == 'Short' and live_ask_price < latest_lower_band:
                            closing_volume = min(abs(self.open_order_volume), abs(live_ask_volume))
                            orders.append(Order('STARFRUIT', live_ask_price, closing_volume))
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
                        elif self.position_type == 'Long' and live_bid_price > latest_upper_band:
                            closing_volume = min(abs(self.open_order_volume), abs(live_bid_volume))
                            orders.append(Order('STARFRUIT', live_bid_price, -closing_volume))
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
                        if self.position_type == 'Short' and (live_ask_price < latest_lower_band or live_ask_price < self.latest_price):
                            order_quantity = min(abs(self.remaining_quantity), abs(live_ask_volume))
                            orders.append(Order('STARFRUIT', live_ask_price, order_quantity))
                            self.remaining_quantity -= order_quantity
                            if self.remaining_quantity > 0:
                                self.partially_closed = True
                                self.position_open = True
                                self.position_type = 'Short'
                            else:
                                self.partially_closed = False
                                self.position_open = False
                        elif self.position_type == 'Long' and (live_bid_price > latest_upper_band or live_bid_price > self.latest_price):
                            order_quantity = min(abs(self.remaining_quantity), abs(live_bid_volume))
                            orders.append(Order('STARFRUIT', live_bid_price, -order_quantity))
                            self.remaining_quantity -= order_quantity
                            if self.remaining_quantity > 0:
                                self.partially_closed = True
                                self.position_open = True
                                self.position_type = 'Long'
                            else:
                                self.partially_closed = False
                                self.position_open = False
            
            traderData = jsonpickle.encode(self)
            result['STARFRUIT'] = orders
            
        return result, conversions, traderData