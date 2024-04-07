import jsonpickle
import numpy as np
import pandas as pd
from datamodel import TradingState, Order
from typing import List

class Trader:
    def __init__(self):
        # Constants
        # self.am_std_multiplier = 1.8
        # self.am_window_size = 34
        self.star_std_multiplier = 1.6
        self.star_window_size = 37
        # Variables
        self.star_position_open = False
        self.star_position_type = None
        self.star_historical_bid_prices = []
        self.star_historical_ask_prices = []
        self.star_open_order_volume = 0
        self.star_partially_closed = False
        self.star_latest_price = 0

        # Alex added these
        self.star_just_opened = False
        self.star_initial_position = 0

    def run(self, state: TradingState):

#--------------------------------------------------------------------------------------------------------------
        # Load the saved state
        if state.traderData:
            saved_state = jsonpickle.decode(state.traderData)
            # Constants
            # self.am_std_multiplier = saved_state.am_std_multiplier
            # self.am_window_size = saved_state.am_window_size
            self.star_std_multiplier = saved_state.star_std_multiplier
            self.star_window_size = saved_state.star_window_size

            # Variables
            self.star_position_open = saved_state.star_position_open
            self.star_position_type = saved_state.star_position_type
            self.star_historical_bid_prices = saved_state.star_historical_bid_prices
            self.star_historical_ask_prices = saved_state.star_historical_ask_prices
            self.star_open_order_volume = saved_state.star_open_order_volume
            self.star_partially_closed = saved_state.star_partially_closed
            self.star_latest_price = saved_state.star_latest_price

            # Alex added these
            self.star_just_opened = saved_state.star_just_opened
            self.star_initial_position = saved_state.star_initial_position

        print(len(self.star_historical_bid_prices))
        print(len(self.star_historical_ask_prices))
        print('star open' if self.star_position_open else 'star closed')
        print('Position: ', state.position)
#--------------------------------------------------------------------------------------------------------------
        result = {}
        conversions = 1

        # STARFRUIT STRATEGY
        if 'STARFRUIT' in state.order_depths:
            star_order_depth = state.order_depths['STARFRUIT']
            star_orders = []
            star_position = state.position.get('STARFRUIT', 0)

            # Get the total position of STARFRUIT
            if self.star_just_opened:
                self.star_initial_position = star_position
                self.star_just_opened = False

            # Check if the position has been closed
            if star_position == 0:
                self.star_initial_position = 0
                self.star_position_open = False
                self.star_partially_closed = False
            # Check if the position has been partially closed
            elif self.star_position_open and self.star_position_type == 'Long' and self.star_initial_position > star_position:
                self.star_position_open = True
                self.star_partially_closed = True
            elif self.star_position_open and self.star_position_type == 'Short' and self.star_initial_position < star_position:
                self.star_position_open = True
                self.star_partially_closed = True

            # Get the highest bid price and lowest ask price and append to historical bid and ask prices
            if star_order_depth.buy_orders and star_order_depth.sell_orders:
                star_bid_price = max(star_order_depth.buy_orders)
                self.star_historical_bid_prices.append(star_bid_price)
                star_ask_price = min(star_order_depth.sell_orders)
                self.star_historical_ask_prices.append(star_ask_price)

            # Get the second highest bid price and volume
            if len(star_order_depth.buy_orders) > 1:
                star_bid_price_2 = sorted(star_order_depth.buy_orders, reverse=True)[1] # Sort by key in descending order
            else:
                star_bid_price_2 = None

            # Get the second lowest ask price and volume
            if len(star_order_depth.sell_orders) > 1:
                star_ask_price_2 = sorted(star_order_depth.sell_orders)[1] # Sort by key in ascending order
            else:
                star_ask_price_2 = None

            # If there are enough historical prices, calculate the rolling mean and standard deviation
            if len(self.star_historical_bid_prices) > 37:
                # Calculate the rolling mean and standard deviation for the bid prices(upper band)
                star_bid_rolling_mean = pd.Series(self.star_historical_bid_prices).rolling(window=self.star_window_size).mean()
                star_bid_rolling_std = pd.Series(self.star_historical_bid_prices).rolling(window=self.star_window_size).std()
                star_upper_band = star_bid_rolling_mean + star_bid_rolling_std.values * self.star_std_multiplier

                # Calculate the rolling mean and standard deviation for the ask prices(lower band)
                star_ask_rolling_mean = pd.Series(self.star_historical_ask_prices).rolling(window=self.star_window_size).mean()
                star_ask_rolling_std = pd.Series(self.star_historical_ask_prices).rolling(window=self.star_window_size).std()
                star_lower_band = star_ask_rolling_mean - star_ask_rolling_std.values * self.star_std_multiplier

                # Get the latest upper and lower bands
                star_latest_upper_band = star_upper_band.iloc[-1]
                print(star_latest_upper_band)
                star_latest_lower_band = star_lower_band.iloc[-1]
                print(star_latest_lower_band)

                # Get the latest bid and ask prices and volumes
                star_live_ask_price, star_live_ask_volume = list(star_order_depth.sell_orders.items())[0]
                star_live_bid_price, star_live_bid_volume = list(star_order_depth.buy_orders.items())[0]

                print(self.star_position_open)
                print(star_position)
                print(self.star_open_order_volume)

                # If the position has not been opened, check if the position can be opened
                if not self.star_position_open:
                    if star_live_bid_price > star_latest_upper_band:    # Short position
                        self.star_open_order_volume = min(abs(star_live_bid_volume), 20)
                        star_orders.append(Order('STARFRUIT', star_live_bid_price, -self.star_open_order_volume))
                        print("star open upper")
                        self.star_latest_price = star_live_bid_price
                        self.star_position_open = True
                        self.star_position_type = 'Short'
                    
                    elif star_live_ask_price < star_latest_lower_band:  # Long position
                        self.star_open_order_volume = min(abs(star_live_ask_volume), 20)
                        star_orders.append(Order('STARFRUIT', star_live_ask_price, self.star_open_order_volume))

                        # If there is not enough volume to open the position, create a second order at new price
                        if self.star_open_order_volume < 20 and star_ask_price_2:   # Check if there is a second ask price
                            open_order_volume_2 = 20 - self.star_open_order_volume
                            open_order_price_2 = (star_live_ask_price - star_ask_price_2) / 2
                            star_orders.append(Order('STARFRUIT', open_order_price_2, open_order_volume_2))
                            print("star open second lower")

                        print("star open lower")
                        self.star_latest_price = star_live_ask_price
                        self.star_position_open = True
                        self.star_position_type = 'Long'
                        self.star_just_opened = True
                        
                # If the position has not received a closing signal, check if the position can be added to
                elif self.star_position_open and not self.star_partially_closed:

                    if self.star_position_type == 'Long' and star_live_ask_price < star_latest_lower_band:
                        star_additional_volume = min((20 - star_position), abs(star_live_ask_volume))
                        star_orders.append(Order('STARFRUIT', star_live_ask_price, star_additional_volume))
                        
                        print("additional long position")
                        self.star_just_opened = True
                        self.star_position_open = True
                        self.star_position_type = 'Long'
                    
                    elif self.star_position_type == 'Short' and star_live_bid_price > star_latest_upper_band:
                        star_additional_volume = min(abs(20-star_position), abs(star_live_bid_volume))
                        star_orders.append(Order('STARFRUIT', star_live_bid_price, -star_additional_volume))
                        
                        print("additional short position")
                        self.star_initial_position += star_additional_volume # Add to the initial position
                        self.star_position_open = True
                        self.star_position_type = 'Short'

                # If the position has received a closing signal, continue to close the position
                elif self.star_position_open and self.star_partially_closed:
                    
                    if self.star_position_type == 'Short' and star_live_ask_price < star_latest_lower_band:

                        star_closing_volume = min(abs(star_position), abs(star_live_ask_volume)) # Caps volume to the position size
                        star_orders.append(Order('STARFRUIT', star_live_ask_price, star_closing_volume))
                    
                    elif self.star_position_type == 'Long' and star_live_bid_price > star_latest_upper_band:
                        star_closing_volume = min(abs(star_position), abs(star_live_bid_volume)) # Caps volume to the position size
                        star_orders.append(Order('STARFRUIT', star_live_bid_price, -star_closing_volume))
                        
                        # If there wasnt enough volume to close the position, create a second order at new price
                        if (star_position - star_closing_volume) > 0 and star_bid_price_2:

                            # Calculate favorble price and quantity for second order
                            star_order_quantity_2 = star_position - star_closing_volume
                            star_order_price_2 = (star_live_bid_price - star_bid_price_2) / 2
                            star_orders.append(Order('STARFRUIT', star_order_price_2, -star_order_quantity_2))

                    # If star is partially closed, continue to close the position
                    elif self.star_partially_closed:
                        
                        # Short position
                        if self.star_position_type == 'Short' and (star_live_ask_price < star_latest_lower_band or star_live_ask_price < self.star_latest_price):
                            star_order_quantity = min(abs(star_position), abs(star_live_ask_volume))
                            star_orders.append(Order('STARFRUIT', star_live_ask_price, star_order_quantity))

                        # Long position
                        elif self.star_position_type == 'Long' and (star_live_bid_price > star_latest_upper_band or star_live_bid_price > self.star_latest_price):
                            star_order_quantity = min(abs(star_position), abs(star_live_bid_volume))
                            star_orders.append(Order('STARFRUIT', star_live_bid_price, -star_order_quantity))

                            # If there wasnt enough volume to close the position, create a second order at new price
                            if (star_position - star_order_quantity) > 0 and star_bid_price_2:  # Check if there is a second bid price
                                star_order_quantity_2 = star_position - star_order_quantity
                                star_order_price_2 = (star_live_bid_price - star_bid_price_2) / 2
                                star_orders.append(Order('STARFRUIT', star_order_price_2, -star_order_quantity_2))

            result['STARFRUIT'] = star_orders
            traderData = jsonpickle.encode(self)
            
        return result, conversions, traderData