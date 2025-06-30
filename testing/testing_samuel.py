import sys
sys.path.insert(1, "/home/bygl/Documents/Dev/simeis/example")

from client import Game
from client import SimeisError
import unittest
import random, string

def randomword(length):
   letters = string.ascii_lowercase
   return ''.join(random.choice(letters) for i in range(length))


class BaseScenarioTest(unittest.TestCase):
    def test_example_scenario(self):
        # new player created
        game = Game(randomword(32)) # new player with random username each time
        # print("test")
    
        try:
            game.get(f"/player/{game.pid}")
        except SimeisError:
            self.assertTrue(f"No player was found with this ID: {game.pid}" in context.SimeisError)
            print("Fail: the player wasn't created")
            pass

        print("Pass: player created")

        status = game.get(f"/player/{game.pid}")
        game.sta = list(status["stations"].keys())[0]
        station = game.get(f"/station/{game.sta}")

        # thune de départ
        initmoney = 72000.0
        player_money = float(game.get_player_money())
        self.assertEqual(player_money, initmoney)

        print("Pass: valid initial money")

        # acheter un vaisseau
        money_before = float(game.get_player_money())
        
        try:
            game.buy_first_ship(game.sta)
        except SimeisError:
            self.assertTrue(f"Not enough money" in context.SimeisError)

        print("Pass: ship bought")

        status = game.get(f"/player/{game.pid}") # Update our status
        ship = status["ships"][0]

        for ship in status["ships"]:
            sid = ship["id"]
            game.sid.append(sid)
        
        money_after = float(game.get_player_money())

        self.assertLess(money_after, money_before)

        print("Pass: less money after buying ship")

        # acheter un module
        money_before = game.get_player_money()
        
        try:
            game.buy_first_mining_module("Miner", game.sta, game.sid[0])
        except SimeisError:
            self.assertTrue(f"Not enough money" in context.SimeisError)

        print("Pass: module bought")
        
        money_after = game.get_player_money()

        self.assertLess(money_after, money_before)

        print("Pass: less money after buying module")


        print("All test passed")


testScenario = BaseScenarioTest()
testScenario.test_example_scenario()