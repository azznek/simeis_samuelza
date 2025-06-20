PORT=8080
URL=f"http://0.0.0.0:{PORT}"

import os
import sys
import math
import time
import json
import string
import urllib.request

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
        self.pid = self.player["playerId"] # ID of our player
        self.sid = None    # ID of our ship
        self.sta = None    # ID of our station

        self.last_hullplate_values = []


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
        reply = urllib.request.urlopen(qry, timeout=1)

        data = json.loads(reply.read().decode())
        err = data.pop("error")
        if err != "ok":
            raise SimeisError(err)

        return data

    def disp_status(self):
        status = game.get("/player/" + str(game.pid))
        print("[*] Current status: {} credits, costs: {}, time left before lost: {} secs".format(
            round(status["money"], 2), round(status["costs"], 2), int(status["money"] / status["costs"]),
        ))

    def percentage_dif(self, val1, val2):
        return (val1-val2) / ((val1+val2) / 2)

    def disp_market(self):
        market = game.get('/market/prices')
        prices = market['prices']

        """ previous_market_prices = None

        if self.previous_market_values is None:
            self.previous_market_values = market
            previous_market_prices = prices
        else:
            previous_market_prices = self.previous_market_values['prices'] """

        print("[*] Current market: ")
        for key, value in prices.items():
            print(f" - {key}: {value}")
        
        hull_plates_value = prices['HullPlate']
        fuel_value = prices['Fuel']

        # fuel_percentage = self.percentage_dif(previous_market_prices['Fuel'], fuel_value)
        # hull_plates_percentage = self.percentage_dif(previous_market_prices['HullPlate'], hull_plates_value)

        del prices['Fuel']
        del prices['HullPlate']

        cheapest_material = min(prices, key=prices.get)
        priciest_material = max(prices, key=prices.get)

        print(f"\nFUEL: {str(fuel_value)}")
        print(f"HULL PLATES: {str(hull_plates_value)}")
        print(f"\nCHEAPEST MATERIAL: {cheapest_material} ({prices[cheapest_material]})")
        print(f"PRICIEST MATERIAL: {priciest_material} ({prices[priciest_material]})")

        # self.previous_market_values = market

    def should_do_repairs(self):
        ship = self.get(f"/ship/{self.sid}")
        market = game.get('/market/prices')
        prices = market['prices']
        current_hullplates_value = prices["HullPlate"]

        current_hull_decay = ship["hull_decay"]
        hull_decay_capacity = ship["hull_decay_capacity"]

        print(f"[*] Current hull decay level: {current_hull_decay}/{hull_decay_capacity}")
        
        # if hull decay is above three quarters of decay capacity, repair anyway
        if current_hull_decay >= hull_decay_capacity/4*3: 
            self.last_hullplate_values.append(current_hullplates_value)
            print('[*] REPAIRS REQUIRED - Hull decay at more than three quarters of capacity')
            return True


        # safeguarding condition
        if self.last_hullplate_values == []:
            self.last_hullplate_values.append(current_hullplates_value)
            print('[*] REPAIRS SKIPPED - No prices monitoring can be done yet')
            return False


        # give a buy score to the current hull plate value 
        buy_score = hull_decay_capacity
        for index, value in enumerate(self.last_hullplate_values):
            if index >= 20:
                break
            if current_hullplates_value < value:
                buy_score -= hull_decay_capacity/10

        # compare buy score to current hull decay
        # if buy score is smaller than hull decay then repair
        if current_hull_decay > buy_score:
            self.last_hullplate_values.append(current_hullplates_value)
            print(f'[*] REPAIRS REQUIRED - The hull plate price is optimal (score: {buy_score})')
            return True
        else:
            self.last_hullplate_values.append(current_hullplates_value)
            print(f"[*] NO REPAIRS REQUIRED - The hull plate price isn't optimal (score: {buy_score})")
            return False





    # If we have a file containing the player ID and key, use it
    # If not, let's create a new player
    # If the player has lost, print an error message
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

    def hire_first_pilot(self, sta, ship):
        # Hire a pilot, and assign it to our ship
        pilot = self.get(f"/station/{sta}/crew/hire/pilot")["id"]
        self.get(f"/station/{sta}/crew/assign/{pilot}/{ship}/pilot")

    def hire_first_trader(self, sta):
        # Hire a trader, assign it on our station
        trader = self.get(f"/station/{sta}/crew/hire/trader")["id"]
        self.get(f"/station/{sta}/crew/assign/{trader}/trading")

    def travel(self, sid, pos):
        costs = self.get(f"/ship/{sid}/navigate/{pos[0]}/{pos[1]}/{pos[2]}")
        print("[*] Traveling to {}, will take {}".format(pos, costs["duration"]))
        self.wait_idle(sid, ts=costs["duration"])

    def wait_idle(self, sid, ts=2):
        ship = self.get(f"/ship/{sid}")
        while ship["state"] != "Idle":
            time.sleep(ts)
            ship = self.get(f"/ship/{sid}")

    # Repair the ship:     Buy the plates, then ask for reparation
    def ship_repair(self, sid):
        ship = self.get(f"/ship/{sid}")
        req = int(ship["hull_decay"])

        # No need for any reparation
        if req == 0:
            return

        # In case we don't have enough hull plates in stock
        station = self.get(f"/station/{self.sta}")["cargo"]
        if "HullPlate" not in station["resources"]:
            station["resources"]["HullPlate"] = 0
        if station["resources"]["HullPlate"] < req:
            need = req - station["resources"]["HullPlate"]
            bought = self.get(f"/market/{self.sta}/buy/hullplate/{need}")
            print(f"[*] Bought {need} of hull plates for", bought["removed_money"])
            station = self.get(f"/station/{self.sta}")["cargo"]

        if station["resources"]["HullPlate"] > 0:
            # Use the plates in stock to repair the ship
            repair = self.get(f"/station/{self.sta}/repair/{self.sid}")
            print("[*] Repaired {} hull plates on the ship".format(repair["added-hull"]))

    # Refuel the ship:    Buy the fuel, then ask for a refill
    def ship_refuel(self, sid):
        ship = self.get(f"/ship/{sid}")
        req = int(ship["fuel_tank_capacity"] - ship["fuel_tank"])

        # No need for any refuel
        if req == 0:
            return

        # In case we don't have enough fuel in stock
        station = self.get(f"/station/{self.sta}")["cargo"]
        if "Fuel" not in station["resources"]:
            station["resources"]["Fuel"] = 0
        if station["resources"]["Fuel"] < req:
            need = req - station["resources"]["Fuel"]
            bought = self.get(f"/market/{self.sta}/buy/Fuel/{need}")
            print(f"[*] Bought {need} of fuel for", bought["removed_money"])
            station = self.get(f"/station/{self.sta}")["cargo"]

        if station["resources"]["Fuel"] > 0:
            # Use the fuel in stock to refill the ship
            refuel = self.get(f"/station/{self.sta}/refuel/{self.sid}")
            print("[*] Refilled {} fuel on the ship for {} credits".format(
                refuel["added-fuel"],
                bought["removed_money"],
            ))

    # Initializes the game:
    #     - Ensure our player exists
    #     - Ensure our station has a Trader hired
    #     - Ensure we own a ship
    #     - Setup the ship
    #         - Hire a pilot & assign it to our ship
    #         - Buy a mining module to be able to farm
    #         - Hire an operator & assign it on the mining module of our ship
    def init_game(self):
        # Ensure we own a ship, buy one if we don't
        status = self.get(f"/player/{self.pid}")
        self.sta = list(status["stations"].keys())[0]
        station = self.get(f"/station/{self.sta}")

        if not check_has(station["crew"], "member_type", "Trader"):
            self.hire_first_trader(self.sta)
            print("[*] Hired a trader, assigned it on station", self.sta)

        if len(status["ships"]) == 0:
            self.buy_first_ship(self.sta)
            status = self.get(f"/player/{self.pid}") # Update our status
        ship = status["ships"][0]
        self.sid = ship["id"]

        # Ensure our ship has a crew, hire one if we don't
        if not check_has(ship["crew"], "member_type", "Pilot"):
            self.hire_first_pilot(self.sta, self.sid)
            print("[*] Hired a pilot, assigned it on ship", self.sid)

        print("[*] Game initialisation finished successfully")

    # - Find the nearest planet we can mine
    # - Go there
    # - Fill our cargo with resources
    # - Once the cargo is full, we stop mining, and this function returns
    def go_mine(self):
        print("[*] Starting the Mining operation")

        # Scan the galaxy sector, detect which planet is the nearest
        station = self.get(f"/station/{self.sta}")
        planets = self.get(f"/station/{self.sta}/scan")["planets"]
        nearest = sorted(planets,
            key=lambda pla: get_dist(station["position"], pla["position"])
        )[0]

        # If the planet is solid, we need a Miner to mine it
        # If it's gaseous, we need a GasSucker to mine it
        if nearest["solid"]:
            modtype = "Miner"
        else:
            modtype = "GasSucker"

        # Ensure the ship has a corresponding module, buy one if we don't
        ship = self.get(f"/ship/{self.sid}")
        if not check_has(ship["modules"], "modtype", modtype):
            self.buy_first_mining_module(modtype, self.sta, self.sid)
        print("[*] Targeting planet at", nearest["position"])

        self.wait_idle(self.sid) # If we are currently occupied, wait

        # If we are not current at the position of the target planet, travel there
        if ship["position"] != nearest["position"]:
            self.travel(ship["id"], nearest["position"])

        # Now that we are there, let's start mining
        info = self.get(f"/ship/{self.sid}/extraction/start")
        print("[*] Starting extraction:")
        for res, amnt in info.items():
            print(f"\t- Extraction of {res}: {amnt}/sec")

        # Wait until the cargo is full
        self.wait_idle(self.sid) # The ship will have the state "Idle" once the cargo is full
        print("[*] The cargo is full, stopping mining process")

    # - Go back to the station
    # - Unload all the cargo
    # - Sell it on the market
    # - Refuel & repair the ship
    def go_sell(self):
        self.wait_idle(self.sid) # If we are currently occupied, wait
        ship = self.get(f"/ship/{self.sid}")
        station = self.get(f"/station/{self.sta}")

        # If we aren't at the station, got there
        if ship["position"] != station["position"]:
            self.travel(ship["id"], station["position"])

        # Unload the cargo and sell it directly on the market
        for res, amnt in ship["cargo"]["resources"].items():
            if amnt == 0.0:
                continue
            unloaded = self.get(f"/ship/{self.sid}/unload/{res}/{amnt}")
            sold = self.get(f"/market/{self.sta}/sell/{res}/{amnt}")
            print("[*] Unloaded and sold {} of {}, for {} credits".format(
                unloaded["unloaded"], res, sold["added_money"]
            ))

        if self.should_do_repairs():
            self.ship_repair(self.sid)
        self.ship_refuel(self.sid)

if __name__ == "__main__":
    name = sys.argv[1]
    game = Game(name)
    game.init_game()

    while True:
        print("")
        # game.can_skip_repairs()
        game.disp_status()
        game.go_mine()
        game.disp_status()
        # game.disp_market()
        game.go_sell()


