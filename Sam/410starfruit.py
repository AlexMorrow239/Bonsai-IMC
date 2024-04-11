import jsonpickle
import numpy as np
import pandas as pd
from datamodel import TradingState, Order
from typing import List

class Trader:
    def __init__(self):
        self.star_position_open = False
        self.star_position_type = None
        self.star_historical_bid_prices = []
        self.star_historical_ask_prices = []
        self.star_historical_mid_prices = []
        self.ask_bid_historical_spread = []
        self.star_remaining_quantity = 0
        self.star_open_order_volume = 0
        # self.star_partially_closed = False
        self.star_latest_price = 0

    def run(self, state: TradingState):
        if state.traderData:
            saved_state = jsonpickle.decode(state.traderData)
            self.star_position_open = saved_state.star_position_open
            self.star_position_type = saved_state.star_position_type
            self.star_remaining_quantity = saved_state.star_remaining_quantity
            self.star_historical_bid_prices = saved_state.star_historical_bid_prices
            self.star_historical_ask_prices = saved_state.star_historical_ask_prices
            self.star_historical_mid_prices = saved_state.star_historical_mid_prices
            self.star_open_order_volume = saved_state.star_open_order_volume
            # self.star_partially_closed = saved_state.star_partially_closed
            self.star_latest_price = saved_state.star_latest_price
            self.ask_bid_historical_spread = saved_state.ask_bid_historical_spread

        print(len(self.star_historical_bid_prices))
        print(len(self.star_historical_ask_prices))
        print('star open' if self.star_position_open else 'star closed')

        result = {}
        conversions = 1

        if 'STARFRUIT' in state.order_depths:
            star_order_depth = state.order_depths['STARFRUIT']
            star_orders = []

            if star_order_depth.buy_orders and star_order_depth.sell_orders:
                star_bid_price = max(star_order_depth.buy_orders)
                self.star_historical_bid_prices.append(star_bid_price)
                star_ask_price = min(star_order_depth.sell_orders)
                self.star_historical_ask_prices.append(star_ask_price)
                ask_bid_spread = star_ask_price - star_bid_price
                self.ask_bid_historical_spread.append(ask_bid_spread)
                star_mid_price = (star_bid_price+star_ask_price)/2
                self.star_historical_mid_prices.append(star_mid_price)
                ask_bid_spread = star_ask_price - star_bid_price
                self.ask_bid_historical_spread.append(ask_bid_spread)

            if len(self.star_historical_bid_prices) > 0:

                try:
                    star_live_ask_price_2, star_live_ask_volume_2 = list(star_order_depth.sell_orders.items())[1]
                    star_live_bid_price_2, star_live_bid_volume_2 = list(star_order_depth.buy_orders.items())[1]
                except:
                    pass
                    
                star_live_ask_price, star_live_ask_volume = list(star_order_depth.sell_orders.items())[0]
                star_live_bid_price, star_live_bid_volume = list(star_order_depth.buy_orders.items())[0]
                live_mid_price = (star_live_ask_price + star_live_bid_price)/2
                prev_mid_price = self.star_historical_mid_prices[-2]
                live_ask_bid_spread = star_live_ask_price - star_live_bid_price

                print(prev_mid_price)
                print(self.star_position_open)
                print(self.star_remaining_quantity)
                print(self.star_open_order_volume)

                if not self.star_position_open:
                    if live_ask_bid_spread <= 3 and live_mid_price <= prev_mid_price:
                        self.star_open_order_volume = min(abs(star_live_ask_volume), 2)
                        star_orders.append(Order('STARFRUIT', star_live_ask_price, self.star_open_order_volume))
                        print("star open lower")
                        self.star_latest_price = star_live_ask_price
                        self.star_position_open = True
                        self.star_position_type = 'Long'
                        self.star_remaining_quantity = self.star_open_order_volume
                    elif live_ask_bid_spread <= 3 and live_mid_price >= prev_mid_price:
                        self.star_open_order_volume = min(abs(star_live_bid_volume), 2)
                        star_orders.append(Order('STARFRUIT', star_live_bid_price, -self.star_open_order_volume))
                        print("star open upper")
                        self.star_latest_price = star_live_bid_price
                        self.star_position_open = True
                        self.star_position_type = 'Short'
                        self.star_remaining_quantity = self.star_open_order_volume
                        
                elif self.star_position_open:
                    # if self.star_position_type == 'Long' and ask_bid_spread <= 3 and live_mid_price <= prev_mid_price:
                    #     star_additional_volume = min(abs(20-self.star_remaining_quantity), abs(star_live_ask_volume))
                    #     star_orders.append(Order('STARFRUIT', star_live_ask_price, star_additional_volume))
                    #     self.star_remaining_quantity += star_additional_volume
                    #     print("additional long position")
                    #     self.star_position_open = True
                    #     self.star_position_type = 'Long'
                    # elif self.star_position_type == 'Short' and ask_bid_spread <= 3 and live_mid_price >= prev_mid_price:
                    #     star_additional_volume = min(abs(20-self.star_remaining_quantity), abs(star_live_bid_volume))
                    #     star_orders.append(Order('STARFRUIT', star_live_bid_price, -star_additional_volume))
                    #     self.star_remaining_quantity += star_additional_volume
                    #     print("additional short position")
                    #     self.star_position_open = True
                    #     self.star_position_type = 'Short'
                    if self.star_position_type == 'Short' and live_ask_bid_spread <= 3 and live_mid_price <= prev_mid_price:
                        star_closing_volume = min(abs(star_live_ask_volume), self.star_remaining_quantity)
                        star_orders.append(Order('STARFRUIT', star_live_ask_price, star_closing_volume))
                        if self.star_remaining_quantity > star_closing_volume:
                            self.star_remaining_quantity -= star_closing_volume
                            star_orders.append(Order('STARFRUIT', star_live_ask_price_2, self.star_remaining_quantity))
                            print("star partial close upper")
                            # self.star_partially_closed = True
                            self.star_position_open = True
                            self.star_position_type = 'Short'
                        elif self.star_remaining_quantity == star_closing_volume:
                            print("star full close upper")
                            self.star_position_open = False
                            # self.star_partially_closed = False
                            self.star_remaining_quantity -= star_closing_volume
                    elif self.star_position_type == 'Long' and live_ask_bid_spread <= 3 and live_mid_price >= prev_mid_price:
                        star_closing_volume = min(abs(star_live_bid_volume), self.star_remaining_quantity)
                        star_orders.append(Order('STARFRUIT', star_live_bid_price, -star_closing_volume))
                        if self.star_remaining_quantity > star_closing_volume:
                            self.star_remaining_quantity -= star_closing_volume
                            star_orders.append(Order('STARFRUIT', star_live_bid_price_2, -self.star_remaining_quantity))
                            print("star partial close lower")
                            # self.star_partially_closed = True
                            self.star_position_open = True
                            self.star_position_type = 'Long'
                        elif self.star_remaining_quantity == star_closing_volume:
                            print("star full close lower")
                            # self.star_partially_closed = False
                            self.star_position_open = False
                            self.star_remaining_quantity -= star_closing_volume
                                
                    # elif self.star_partially_closed:
                    #     # if self.star_position_type == 'Long' and ask_bid_spread <= 3 and live_mid_price <= prev_mid_price:
                    #     #     star_additional_volume = min(abs(20-self.star_remaining_quantity), abs(star_live_ask_volume))
                    #     #     star_orders.append(Order('STARFRUIT', star_live_ask_price, star_additional_volume))
                    #     #     self.star_remaining_quantity += star_additional_volume
                    #     #     print("additional long position")
                    #     #     self.star_position_open = True
                    #     #     self.star_position_type = 'Long'
                    #     # elif self.star_position_type == 'Short' and ask_bid_spread <= 3 and live_mid_price >= prev_mid_price:
                    #     #     star_additional_volume = min(abs(20-self.star_remaining_quantity), abs(star_live_bid_volume))
                    #     #     star_orders.append(Order('STARFRUIT', star_live_bid_price, -star_additional_volume))
                    #     #     self.star_remaining_quantity += star_additional_volume
                    #     #     print("additional short position")
                    #     #     self.star_position_open = True
                    #     #     self.star_position_type = 'Short'
                    #     if self.star_position_type == 'Short' and self.star_latest_price > star_live_ask_price:
                    #         star_order_quantity = min(abs(star_live_ask_volume), self.star_remaining_quantity)
                    #         star_orders.append(Order('STARFRUIT', star_live_ask_price, star_order_quantity))
                    #         if self.star_remaining_quantity > star_order_quantity:
                    #             self.star_partially_closed = True
                    #             self.star_position_open = True
                    #             self.star_position_type = 'Short'
                    #             self.star_remaining_quantity -= star_order_quantity
                    #         elif self.star_remaining_quantity == star_order_quantity:
                    #             self.star_position_open = False
                    #             self.star_partially_closed = False
                    #             self.star_remaining_quantity -= star_order_quantity
                    #         elif self.star_remaining_quantity < star_order_quantity:
                    #             print("star full close upper + open lower")
                    #             self.star_latest_price = star_live_ask_price
                    #             self.star_position_open = True
                    #             self.star_partially_closed = False
                    #             self.star_position_type = 'Long'
                    #             self.star_remaining_quantity = (star_order_quantity - self.star_remaining_quantity)
                    #     elif self.star_position_type == 'Long' and self.star_latest_price < star_live_ask_price:
                    #         star_order_quantity = min(abs(star_live_bid_volume), self.star_remaining_quantity)
                    #         star_orders.append(Order('STARFRUIT', star_live_bid_price, -star_order_quantity))
                    #         if self.star_remaining_quantity > star_order_quantity:
                    #             self.star_partially_closed = True
                    #             self.star_position_open = True
                    #             self.star_position_type = 'Long'
                    #             self.star_remaining_quantity -= star_order_quantity
                    #         elif self.star_remaining_quantity == star_order_quantity:
                    #             self.star_partially_closed = False
                    #             self.star_position_open = False
                    #             self.star_remaining_quantity -= star_order_quantity
                    #         elif self.star_remaining_quantity < star_order_quantity:
                    #             print("star full close lower + open upper")
                    #             self.star_latest_price = star_live_bid_price
                    #             self.star_position_open = True
                    #             self.star_partially_closed = False
                    #             self.star_position_type = 'Short'
                    #             self.star_remaining_quantity = (star_order_quantity - self.star_remaining_quantity)
            
            traderData = jsonpickle.encode(self)
            result['STARFRUIT'] = star_orders
            
        return result, conversions, traderData