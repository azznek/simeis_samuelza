import sys


import unittest
import random, string
import os
import sys
import math
import json
import string
import urllib.request

PORT=8080

TESTING_PORT=9345
URL=f"http://127.0.0.1:{TESTING_PORT}"



class SimeisError(Exception):
    pass

# Théorème de Pythagore pour récupérer la distance entre 2 points dans l'espace 3D
def get_dist(a, b):
    return math.sqrt(((a[0] - b[0]) ** 2) + ((a[1] - b[1]) ** 2) + ((a[2] - b[2]) ** 2))

# Check if types are present in the list
def check_has(alld, key, *req):
    alltypes = [c[key] for c in alld.values()]
    return all([k in alltypes for k in req])

class Game:
    def __init__(self, username):
        # Init connection & setup player
        assert self.get("/ping")["ping"] == "pong"
        print("[*] Connection to server OK")
        self.setup_player(username)

        # Useful for our game loops
        self.pid = self.player["playerId"]
        self.sid = []
        self.sta = None
        
    def get(self, path, **qry):
        if hasattr(self, "player"):
            qry["key"] = self.player["key"]

        tail = ""
        if len(qry) > 0:
            tail += "?"
            tail += "&".join([
                "{}={}".format(k, urllib.parse.quote(v)) for k, v in qry.items()
            ])

        qry = f"{URL}{path}{tail}"
        reply = urllib.request.urlopen(qry, timeout=10)

        data = json.loads(reply.read().decode())
        err = data.pop("error")
        if err != "ok":
            raise SimeisError(err)

        return data
    
    def setup_player(self, username, force_register=False):
        # Sanitize the username, remove any symbols
        username = "".join([c for c in username if c in string.ascii_letters + string.digits]).lower()

        # If we don't have any existing account
        if force_register or not os.path.isfile(f"./{username}.json"):
            player = self.get(f"/player/new/{username}")
            with open(f"./{username}.json", "w") as f:
                json.dump(player, f, indent=2)       
            print(f"[*] Created player {username}")
            self.player = player

        # If an account already exists
        else:
            with open(f"./{username}.json", "r") as f:
                self.player = json.load(f)
            print(f"[*] Loaded data for player {username}")

        # Try to get the profile
        try:
            player = self.get("/player/{}".format(self.player["playerId"]))

        # If we fail, that must be that the player doesn't exist on the server
        except SimeisError:
            # And so we retry but forcing to register a new account
            return self.setup_player(username, force_register=True)

        # If the player already failed, we must reset the server
        # Or recreate an account with a new nickname
        if player["money"] <= 0.0:
            print("!!! Player already lost, please restart the server to reset the game")
            sys.exit(0)
    
    def get_player_money(self):
        return self.get(f"/player/{self.pid}")["money"]
    
    def buy_first_ship(self, sta):
        # Get all the ships available for purchasing in the station
        available = self.get(f"/station/{sta}/shipyard/list")["ships"]
        # Get the cheapest option
        cheapest = sorted(available, key = lambda ship: ship["price"])[0]
        print("[*] Purchasing the first ship for {} credits".format(cheapest["price"]))
        # Buy it
        self.get(f"/station/{sta}/shipyard/buy/" + str(cheapest["id"]))
    
    def buy_first_mining_module(self, modtype, sta, sid):
        # Buy the mining module
        all = self.get(f"/station/{sta}/shop/modules")
        mod_id = self.get(f"/station/{sta}/shop/modules/{sid}/buy/{modtype}")["id"]

        # Check if we have the crew assigned on this module
        # If not, hire an operator, and assign it to the mining module of our ship
        ship = self.get(f"/ship/{sid}")
        if not check_has(ship["crew"], "member_type", "Operator"):
            op = self.get(f"/station/{sta}/crew/hire/operator")["id"]
            self.get(f"/station/{sta}/crew/assign/{op}/{sid}/{mod_id}")
  

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