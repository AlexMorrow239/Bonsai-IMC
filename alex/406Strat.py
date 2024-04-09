import jsonpickle
import numpy as np
import pandas as pd
from datamodel import TradingState, Order
from typing import List
from collections import defaultdict

class Trader:
    def __init__(self):
        # Constants
        self.star_std_multiplier = 1.6
        self.star_window_size = 37
        # Variables
        self.position_type = defaultdict(str)
        self.just_opened = defaultdict(bool)
        self.initial_position = defaultdict(int)
        self.bestBidData = defaultdict(list)
        self.bestAskData = defaultdict(list)
        self.position_open = defaultdict(bool)
        self.partially_closed = defaultdict(bool)
    
    def determinePositions(self, order_depths, position_dict):
        for product in order_depths.keys():
            self.position_open[product] = False if position_dict.get(product, 0) == 0 else True


    def appendBestPrices(self, product, order_depth):
        if order_depth.buy_orders and order_depth.sell_orders:
            self.bestBidData[product].append(max(order_depth.buy_orders))
            self.bestAskData[product].append(min(order_depth.sell_orders))
            return True
        
        return False
        

    def calculateBands(self, product, order_depth, window_size, std_multiplier):
        # Get the highest bid price and lowest ask price and append to historical bid and ask prices
        if not self.appendBestPrices(product, order_depth):
            return None, None
        
        productBestBids = self.bestBidData[product]
        productBestAsks = self.bestAskData[product]

        # If there are enough historical prices, calculate the rolling mean and standard deviation
        if len(productBestBids) > window_size:
            # Calculate the rolling mean and standard deviation for the bid prices(upper band)
            bidRollingMean = pd.Series(productBestBids).rolling(window=window_size).mean()
            bidRollingStd = pd.Series(productBestBids).rolling(window=self.star_window_size).std()
            upperBandSeries = bidRollingMean + bidRollingStd.values * std_multiplier  # Series of all upper bands

            # Calculate the rolling mean and standard deviation for the ask prices(lower band)
            askRollingMean = pd.Series(productBestAsks).rolling(window=window_size).mean()
            askRollingStd = pd.Series(productBestAsks).rolling(window=window_size).std()
            lowerBandSeries = askRollingMean - askRollingStd.values * std_multiplier # Series of all lower bands
        else:
            return None, None
        
        return upperBandSeries.iloc[-1], lowerBandSeries.iloc[-1]
    
    def secondBest(self, order_depth, order_type):
        if order_type == 'buy' and len(order_depth.buy_orders) > 1:
            secondBest = sorted(order_depth.buy_orders, reverse=True)[1] # Sort by key in descending order
        elif order_type == 'sell' and len(order_depth.sell_orders) > 1:
            secondBest = sorted(order_depth.sell_orders)[1]
        else:
            secondBest = None      
        return secondBest
    
    def updateProductState(self, product, state):
            product_order_depth = state.order_depths[product]
            product_position = state.position.get(product, 0)
            product_position_type = self.position_type.get(product, None)
            product_initial_position = self.initial_position.get(product, 0)

            # Get the total position of AMETHYSTS
            if self.just_opened[product]:
                self.initial_position[product] = product_position
                self.just_opened[product] = False

            # Check if the position has been closed
            if not self.position_open[product]:
                self.initial_position[product] = 0
                self.partially_closed[product] = False
            # Check if the position has been partially closed (long or short)
            elif self.position_open[product] and product_position_type == 'Long' and product_initial_position > product_position:
                self.position_open[product] = True
                self.partially_closed[product] = True
            elif self.position_open[product] and product_position_type == 'Short' and product_initial_position < product_position:
                self.position_open[product] = True
                self.partially_closed[product] = True
            
            return product_order_depth, product_position
            
    def run(self, state: TradingState):
        result = {}
        conversions = 1

        # Load the saved state
        if state.traderData:
            saved_state = jsonpickle.decode(state.traderData)
            # Constants
            self.star_std_multiplier = saved_state.star_std_multiplier
            self.star_window_size = saved_state.star_window_size
            # Variables
            self.bestBidData = saved_state.bestBidData
            self.bestAskData = saved_state.bestAskData
            self.position_open = saved_state.position_open
            self.position_type = saved_state.position_type
            self.just_opened = saved_state.just_opened
            self.initial_position = saved_state.initial_position
            self.partially_closed = saved_state.partially_closed

        self.determinePositions(state.order_depths, state.position)
        print('Position : ', state.position)
#--------------------------------------------------------------------------------------------------------------
        
        # AMETHYSTS STRATEGY
        if 'AMETHYSTS' in state.order_depths:
            am_orders = []
            # Update the state of AMETHYSTS (current position, type, partially closed, etc.)
            am_order_depth, am_position = self.updateProductState('AMETHYSTS', state)
            
            am_latest_upper_band, am_latest_lower_band = self.calculateBands('AMETHYSTS', am_order_depth, self.star_window_size, self.star_std_multiplier)
            # If the bands are not calculated, return the result
            if not am_latest_upper_band or not am_latest_lower_band:
                print("Bands not calculated")
                return result, conversions, jsonpickle.encode(self)

            # Get the latest bid and ask prices and volumes
            am_best_ask = min(am_order_depth.sell_orders)
            am_best_bid = max(am_order_depth.buy_orders)
            am_best_bid_vol = am_order_depth.buy_orders.get(am_best_bid, 0)
            am_best_ask_vol = am_order_depth.sell_orders.get(am_best_ask, 0)

            # Get the second highest bid price
            am_bid_price_2 = self.secondBest(am_order_depth, 'buy')
            am_ask_price_2 = self.secondBest(am_order_depth, 'sell')

            print(am_position)

            # If the position has not been opened, check if the position can be opened
            if not self.position_open['AMETHYSTS']:
                
                if am_best_bid > am_latest_upper_band:    # Short position
                    open_order_quant_1 = min(abs(am_best_bid_vol), 20)
                    am_orders.append(Order('AMETHYSTS', am_best_bid, -open_order_quant_1))
                    self.position_open['AMETHYSTS'] = True
                    self.position_type['AMETHYSTS'] = 'Short'

                    if open_order_quant_1 < 20 and am_bid_price_2:
                        open_order_quant_2 = 20 - open_order_quant_1
                        open_order_price_2 = int(am_best_bid + 1)
                        am_orders.append(Order('AMETHYSTS', open_order_price_2, -open_order_quant_2))
                        print("amethyst open upper plus custom order")
                    else:
                        print("amethyst open upper")
                
                elif am_best_ask < am_latest_lower_band:  # Long position
                    open_order_quant_1 = min(abs(am_best_ask_vol), 20)
                    am_orders.append(Order('AMETHYSTS', am_best_ask, open_order_quant_1))

                    # If there is not enough volume to open the position, create a second order at new price
                    if open_order_quant_1 < 20 and am_ask_price_2:   # Check if there is a second ask price
                        open_order_quant_2 = 20 - open_order_quant_1
                        open_order_price_2 = int(am_best_ask - 1)
                        am_orders.append(Order('AMETHYSTS', open_order_price_2, open_order_quant_2))
                        print("amethyst open lower plus custom order")
                    else:
                        print("amethyst open lower")
                    self.position_open['AMETHYSTS'] = True
                    self.position_type['AMETHYSTS'] = 'Long'
                    self.just_opened['AMETHYSTS'] = True

            # If position has been opened, check if the position can be closed
            elif self.position_open['AMETHYSTS']:                    
                
                # Conditions for closing long and short positions
                position_type = self.position_type['AMETHYSTS']
                if position_type == 'Short' and am_best_ask < am_latest_lower_band:
                    close_order_quant_1 = min(abs(am_position), abs(am_best_ask_vol)) # Caps volume to the position size
                    am_orders.append(Order('AMETHYSTS', am_best_ask, close_order_quant_1))
                    self.partially_closed['AMETHYSTS'] = True

                    if (abs(am_position) - close_order_quant_1) > 0 and am_ask_price_2:
                        # Calculate favorble price and quantity for second order
                        am_order_quantity_2 = abs(am_position) - close_order_quant_1
                        am_order_price_2 = int(am_best_ask - 1)
                        am_orders.append(Order('AMETHYSTS', am_order_price_2, am_order_quantity_2))
                        print("amethyst INITIAL closing short with 2nd order")
                    else:
                        print("amethyst INITIAL closing short")
                
                elif position_type == 'Long' and am_best_bid > am_latest_upper_band:
                    close_order_quant_1 = min(abs(am_position), abs(am_best_bid_vol)) # Caps volume to the position size
                    am_orders.append(Order('AMETHYSTS', am_best_bid, -close_order_quant_1))
                    self.partially_closed['AMETHYSTS'] = True
                    
                    # If there wasnt enough volume to close the position, create a second order at new price
                    if (am_position - close_order_quant_1) > 0 and am_bid_price_2:
                        # Calculate favorble price and quantity for second order
                        am_order_quantity_2 = am_position - close_order_quant_1
                        am_order_price_2 = int(am_best_bid + 1)
                        am_orders.append(Order('AMETHYSTS', am_order_price_2, -am_order_quantity_2))
                        print("amethyst INITIAL closing long with 2nd order")
                    else:
                        print("amethyst INITIAL closing long")
    
                # If the position has not received a closing signal, check if the position can be added to
                if not self.partially_closed['AMETHYSTS']:

                    if position_type == 'Long' and am_best_ask < am_latest_lower_band:
                        am_additional_volume = min((20 - am_position), abs(am_best_ask_vol))
                        am_orders.append(Order('AMETHYSTS', am_best_ask, am_additional_volume))
                        
                        print("additional long position")
                        self.just_opened['AMETHYSTS'] = True
                        self.position_open['AMETHYSTS'] = True
                        self.position_type['AMETHYSTS'] = 'Long'
                    
                    elif position_type == 'Short' and am_best_bid > am_latest_upper_band and am_position != 20:
                        am_additional_volume = min((20 - abs(am_position)), abs(am_best_bid_vol))
                        am_orders.append(Order('AMETHYSTS', am_best_bid, -am_additional_volume))
                        
                        print("additional short position")
                        self.just_opened['AMETHYSTS'] = True
                        self.position_open['AMETHYSTS'] = True
                        self.position_type['AMETHYSTS'] = 'Short'

                # Continue to close position if partially closed
                elif self.partially_closed['AMETHYSTS'] and len(am_orders) == 0:
                    if position_type == 'Short':
                        order_quant_1 = min(abs(am_best_bid_vol), am_position)
                        am_orders.append(Order('AMETHYSTS', am_best_ask, order_quant_1))
                    
                        if order_quant_1 < abs(am_position) and am_ask_price_2:
                            order_quant_2 = abs(am_position) - order_quant_1
                            open_order_price_2 = int(am_best_ask - 1)
                            am_orders.append(Order('AMETHYSTS', open_order_price_2, order_quant_2))
                            print("amethyst closing short with 2nd order")
                        else:
                            print("amethyst closing short")

                    elif position_type == 'Long':
                        order_quant_1 = min(abs(am_best_bid_vol), am_position)
                        am_orders.append(Order('AMETHYSTS', am_best_bid, -order_quant_1))

                        if order_quant_1 < am_position and am_bid_price_2:
                            order_quant_2 = am_position - order_quant_1
                            open_order_price_2 = int(am_best_bid + 1)
                            am_orders.append(Order('AMETHYSTS', open_order_price_2, -order_quant_2))
                            print("amethyst closing long with 2nd order")
                        else:
                            print("amethyst closing long")

            result['AMETHYSTS'] = am_orders
        traderData = jsonpickle.encode(self)
            
        return result, conversions, traderData