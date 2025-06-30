PORT=9345
URL=f"http://127.0.0.1:{PORT}"
   
import os
import sys
import math
import time
import json
import string
import urllib.request
import threading
import logging

class SimeisError(Exception):
    pass

class test_scenari:
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



    def testing_scenarii1(self):


        status = self.get(f"/player/{self.pid}")
        self.sta = list(status["stations"].keys())[0]
        
        start_player_money = self.get(f'/player/{self.pid}')['money']
        #print(f'Start player money : {start_player_money}')


        # Engager un trader et l'assigner à la station
        trader = self.get(f"/station/{self.sta}/crew/hire/trader")["id"]
        self.get(f"/station/{self.sta}/crew/assign/{trader}/trading")

        
       

        # Acheter de l'or pour vérifier le baisse d'argent
        self.get(f'/market/{self.sta}/buy/gold/10')

        player_money_t2 = self.get(f'/player/{self.pid}')['money']
        #print(f'Player money after buy gold : {player_money_t2}')
        assert(player_money_t2 < start_player_money)

        # Vendre l'or pour vérifier l'augmentation de l'argent
        self.get(f'/market/{self.sta}/sell/gold/10')
        player_money_t3 = self.get(f'/player/{self.pid}')['money']
        #print(f'Player money after sell gold : {player_money_t3}')

        assert(player_money_t3 > player_money_t2)
        
        print('Test scenario1 passed')
    

if __name__ == "__main__":
    name = sys.argv[1]
    game = test_scenari(name)
    game.testing_scenarii1()

    
