PORT=8080
#URL=f"http://127.0.0.1:{PORT}"
URL=f"http://103.45.247.164:{PORT}"

import os
import sys
import math
import time
import json
import string
import urllib.request
import threading
import logging
from rich.console import Console
from rich.live import Live
from rich.table import Table
from rich.panel import Panel
from datetime import datetime, timedelta
import shutil


columns, _ = shutil.get_terminal_size()
import time

console = Console()
panel_width = int(columns * 0.6)  # 40% of terminal width
panel_width = max(panel_width, 30)  # Minimum width for safety
class SimeisError(Exception):
    pass

# Théorème de Pythagore pour récupérer la distance entre 2 points dans l'espace 3D
def get_dist(a, b):
    return math.sqrt(((a[0] - b[0]) ** 2) + ((a[1] - b[1]) ** 2) + ((a[2] - b[2]) ** 2))

# Check if types are present in the list
def check_has(alld, key, *req):
    alltypes = [c[key] for c in alld.values()]
    return all([k in alltypes for k in req])

def estimate_gain(kind, id, data):
    if kind == "module":
        current_rank = data["modules"][id]["rank"]
        new_rank = current_rank + 1
        if new_rank > 45:
            return 0.0
        gain_ratio = (new_rank*100  / current_rank) if current_rank > 0 else 200.0
        if data["cargo"]["capacity"] > 10000:
            return (gain_ratio-100)*2
        return gain_ratio-100

    elif kind == "crew":
        current_rank = data["crew"][id]["rank"]
        new_rank = current_rank + 1
        if "Pilot" == data["crew"][id]["member_type"] and new_rank > 20:
            return 0.0
        if "Operator" == data["crew"][id]["member_type"] and new_rank > 200:
            return 0.0
        gain_ratio = (new_rank*100  / current_rank) if current_rank > 0 else 200.0
        if "Operator" == data["crew"][id]["member_type"] and data["cargo"]["capacity"] > 10000:
            return (gain_ratio+-100)*2
        return gain_ratio-100
    
    elif kind == "trader":
        rank = data["crew"][id]["rank"]
        current_fee = 0.26 / (rank ** 1.15)
        new_fee = 0.26 / ((rank + 1) ** 1.15)
        if new_fee <= 0.01:
            return 0
        gain_ratio = (current_fee * 100 / new_fee) if current_fee > 0 else 200.0
        return gain_ratio-100
    elif kind == "ship":
        current_ships = len(data["ships"]) 
        new_ships = current_ships + 1
        gain_ratio = (new_ships * 100 / current_ships) if current_ships > 0 else 200.0
        return gain_ratio - 100
    elif kind == "shipupgrade":
        # Accès à la stat modifiée selon le type
        if id == "ReactorUpgrade":
            current = data["reactor_power"]
            new = current + 1
            if new > 50: return 0
        elif id == "CargoExpansion":
            current = data["cargo"]["capacity"]
            new = current + 100
            if new > 100000: return 0
        elif id == "HullUpgrade":
            current = data["hull_decay_capacity"]
            new = current 
        elif id == "Shield":
            current = data["shield_power"]
            new = current + 0.01
            if new > 20: return 0
        else:
            return 0.0
        gain_ratio = (new*100 / current) if current > 0 else 110.0
        return gain_ratio-100

    return 0.0

class Game:
    def __init__(self, username):
        # Init connection & setup player
        assert self.get("/ping")["ping"] == "pong"
        print("[*] Connection to server OK")
        self.setup_player(username)

        # Useful for our game loops
        self.startTime = datetime.now()
        self.pid = self.player["playerId"]
        self.sid = []
        self.sta = None
        self.number_of_trader_upgrades = 0
        self.last_hullplate_values = []
        self.flips = {}
        self.ready_for_next_step = None
        self.second_ship_bought = False
        self.dashboard_launched_sids = set()
        self.dashboard_lock = threading.Lock()
        # self.UPGRADE_PATH = [
        #     {"type": "cargo", "min_capacity": 350, "threshold_secs": 300},
        #     {"type": "operator", "min_rank": 2, "threshold_secs": 300},
        #     {"type": "reactor", "min_power": 3, "threshold_secs": 300},
        #     {"type": "cargo", "min_capacity": 650, "threshold_secs": 300},
        #     {"type": "module", "min_rank": 25, "threshold_secs": 300},
        #     {"type": "operator", "min_rank": 15, "threshold_secs": 300},
        #     {"type": "pilot", "min_rank": 2, "threshold_secs": 300},
        #     {"type": "reactor", "min_power": 10, "threshold_secs": 300},
        #     {"type": "cargo", "min_capacity": 1500, "threshold_secs": 300}
        # ]

        self.UPGRADE_PATH = [
           {"type": "operator", "min_rank": 2, "threshold_secs": 60},
           {"type": "reactor", "min_power": 3, "threshold_secs": 60},
           {"type": "module", "min_rank": 25, "threshold_secs": 60},
           {"type": "operator", "min_rank": 15, "threshold_secs": 60},
           {"type": "pilot", "min_rank": 2, "threshold_secs": 60},
           {"type": "reactor", "min_power": 10, "threshold_secs": 60},
           {"type": "cargo", "min_capacity": 1500, "threshold_secs": 60}
        ]

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

    def init_game(self):
        # Ensure we own a ship, buy one if we don't
        status = self.get(f"/player/{self.pid}")
        self.sta = list(status["stations"].keys())[0]
        station = self.get(f"/station/{self.sta}")
        self.ready_for_next_step = False
        if not check_has(station["crew"], "member_type", "Trader"):
            self.hire_first_trader(self.sta)
            print("[*] Hired a trader, assigned it on station", self.sta)

        if len(status["ships"]) == 0:
            self.buy_first_ship(self.sta)
            status = self.get(f"/player/{self.pid}") # Update our status

            
        ship = status["ships"][0]

        for ship in status["ships"]:
            sid = ship["id"]
            self.sid.append(sid)
            if not check_has(ship["crew"], "member_type", "Pilot"):
                self.hire_first_pilot(self.sta, sid)
        


        print("[*] Game initialisation finished successfully")

    def buy_first_ship(self, sta):
        # Get all the ships available for purchasing in the station
        available = self.get(f"/station/{sta}/shipyard/list")["ships"]
        # Get the cheapest option
        cheapest = sorted(available, key = lambda ship: ship["price"])[0]
        print("[*] Purchasing the first ship for {} credits".format(cheapest["price"]))
        # Buy it
        self.get(f"/station/{sta}/shipyard/buy/" + str(cheapest["id"]))

    def hire_first_pilot(self, sta, ship):
        # Hire a pilot, and assign it to our ship
        pilot = self.get(f"/station/{sta}/crew/hire/pilot")["id"]
        self.get(f"/station/{sta}/crew/assign/{pilot}/{ship}/pilot")

    def hire_first_trader(self, sta):
        # Hire a trader, assign it on our station
        trader = self.get(f"/station/{sta}/crew/hire/trader")["id"]
        self.get(f"/station/{sta}/crew/assign/{trader}/trading")

    def buy_new_ship_if_ready(self,logger):
        if not self.ready_for_next_step:
            return
        available = self.get(f"/station/{self.sta}/shipyard/list")["ships"]
        logger.info(f'[*] Available ships : {available}')
        if not available:
            logger.info("[*] Ready for new ships but none available")
            return
        most_expensive = sorted(available, key=lambda ship: ship["cargo_capacity"], reverse=True)[0]
        price = most_expensive["price"]
        if self.get_player_money() > price + 10000:
            logger.info("[*] Buying another ship")
            self.get(f"/station/{self.sta}/shipyard/buy/{most_expensive['id']}")
            new_ship = self.get(f"/ship/{most_expensive['id']}")
            new_ship_id = new_ship["id"]
            self.sid.append(new_ship_id)
            self.hire_first_pilot(self.sta, new_ship_id)
            self.ready_for_next_step = False
        else:
            logger.info(f"[*] Available ships with lot of cargo capacity too expensive")

    def get_player_money(self):
        return self.get(f"/player/{self.pid}")["money"]
    
    def disp_status(self):
        status = game.get("/player/" + str(game.pid))
        print("[*] Current status: {} credits, costs: {}, time left before lost: {} secs".format(
            round(status["money"], 2), round(status["costs"], 2), int(status["money"] / status["costs"]),
        ))

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


    def should_do_repairs(self,sid,logger):
        ship = self.get(f"/ship/{sid}")
        market = game.get('/market/prices')
        prices = market['prices']
        current_hullplates_value = prices["HullPlate"]

        current_hull_decay = ship["hull_decay"]
        hull_decay_capacity = ship["hull_decay_capacity"]

        logger.info(f"[*{sid}] Current hull decay level: {current_hull_decay}/{hull_decay_capacity}")
        
        # if hull decay is above three quarters of decay capacity, repair anyway
        if current_hull_decay >= hull_decay_capacity/4*3: 
            self.last_hullplate_values.append(current_hullplates_value)
            logger.info(f'[*{sid}] REPAIRS REQUIRED - Hull decay at more than three quarters of capacity')
            return True


        # safeguarding condition
        if self.last_hullplate_values == []:
            self.last_hullplate_values.append(current_hullplates_value)
            logger.info(f'[*{sid}] REPAIRS SKIPPED - No prices monitoring can be done yet')
            return False


        # give a buy score to the current hull plate value 
        buy_score = hull_decay_capacity
        for index, value in enumerate(self.last_hullplate_values):
            if index >= 20:
                break
            if current_hullplates_value < value:
                buy_score -= hull_decay_capacity/20

        # compare buy score to current hull decay
        # if buy score is smaller than hull decay then repair
        if current_hull_decay > buy_score:
            self.last_hullplate_values.append(current_hullplates_value)
            logger.info(f'[*{sid}] REPAIRS REQUIRED - The hull plate price is optimal (score: {buy_score})')
            return True
        else:
            self.last_hullplate_values.append(current_hullplates_value)
            logger.info(f"[*{sid}] NO REPAIRS REQUIRED - The hull plate price isn't optimal (score: {buy_score})")
            return False
    # If we have a file containing the player ID and key, use it
    # If not, let's create a new player
    # If the player has lost, logger.info an error message
    
    
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

    def go_mine(self,sid,logger):
        logger.info(f"[*{sid}] Starting the Mining operation")

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
        ship = self.get(f"/ship/{sid}")

        if not check_has(ship["modules"], "modtype", modtype):
            self.buy_first_mining_module(modtype, self.sta, sid)
        
        logger.info(f"[*{sid}] Targeting planet at {nearest["position"]}" )

        self.wait_idle(sid) # If we are currently occupied, wait

        # If we are not current at the position of the target planet, travel there
        if ship["position"] != nearest["position"]:
            self.travel(ship["id"], nearest["position"],logger)

        # Now that we are there, let's start mining
        info = self.get(f"/ship/{sid}/extraction/start")
        logger.info(f"[*{sid}] Starting extraction:")
        for res, amnt in info.items():
            logger.info(f"\t- Extraction of {res}: {amnt}/sec")

        # Wait until the cargo is full
        self.wait_idle(sid) # The ship will have the state "Idle" once the cargo is full
        logger.info(f"[*{sid}] The cargo is full, stopping mining process")
    
    
    def travel(self, sid, pos,logger):
        costs = self.get(f"/ship/{sid}/navigate/{pos[0]}/{pos[1]}/{pos[2]}")
        logger.info(f"[*{sid}] Traveling to {pos}, will take {costs["duration"]}")
        self.wait_idle(sid, ts=costs["duration"])

    def wait_idle(self, sid, ts=1):
        ship = self.get(f"/ship/{sid}")
        while ship["state"] != "Idle":
            time.sleep(ts)
            ship = self.get(f"/ship/{sid}")

    # Repair the ship:     Buy the plates, then ask for reparation
    def ship_repair(self, sid,logger):
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
            logger.info(f"[*{sid}] Bought {need} of hull plates for {bought["removed_money"]}")
            station = self.get(f"/station/{self.sta}")["cargo"]

        if station["resources"]["HullPlate"] > 0:
            # Use the plates in stock to repair the ship
            repair = self.get(f"/station/{self.sta}/repair/{sid}")
            logger.info(f"[*{sid}] Repaired {repair["added-hull"]} hull plates on the ship")

    # Refuel the ship:    Buy the fuel, then ask for a refill
    def ship_refuel(self, sid,logger):
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
            logger.info(f"[*{sid}] Bought {need} of fuel for {bought["removed_money"]}")
            station = self.get(f"/station/{self.sta}")["cargo"]

        if station["resources"]["Fuel"] > 0:
            # Use the fuel in stock to refill the ship
            refuel = self.get(f"/station/{self.sta}/refuel/{sid}")
            logger.info(f"[*{sid}] Refilled {refuel["added-fuel"]} fuel on the ship for {bought["removed_money"]} credits")

    # Initializes the game:
    #     - Ensure our player exists
    #     - Ensure our station has a Trader hired
    #     - Ensure we own a ship
    #     - Setup the ship
    #         - Hire a pilot & assign it to our ship
    #         - Buy a mining module to be able to farm
    #         - Hire an operator & assign it on the mining module of our ship
    

    
    # - Find the nearest planet we can mine
    # - Go there
    # - Fill our cargo with resources
    # - Once the cargo is full, we stop mining, and this function returns
    
    

    def optimize_upgrades(self,sid,logger):
        player = self.get(f"/player/{self.pid}")
        money = player["money"]
        ship = self.get(f"/ship/{sid}")
        station= self.get(f"/station/{self.sta}")

        upgrades = []

        # Prévisualisation
        mod_preview = self.get(f"/station/{self.sta}/shop/modules/{sid}/upgrade")
        crew_preview = self.get(f"/station/{self.sta}/crew/upgrade/ship/{sid}")
        ship_upgrades = self.get(f"/station/{self.sta}/shipyard/upgrade")
        station_upgrades = self.get(f"/station/{self.sta}/upgrades")
        available = self.get(f"/station/{self.sta}/shipyard/list")["ships"]

        # Modules
        for mod_id in ship["modules"]:
            mod_id_str = str(mod_id)
            if mod_id_str in mod_preview:
                price = mod_preview[mod_id_str]["price"]
                gain = estimate_gain("module", mod_id, ship)
                upgrades.append(("module", mod_id, price, gain))

        # Crew
        for crew_id in ship["crew"]:
            crew_id_str = str(crew_id)
            if crew_id_str in crew_preview:
                price = crew_preview[crew_id_str]["price"]
                gain = estimate_gain("crew", crew_id, ship)
                upgrades.append(("crew", crew_id, price, gain))

        # Ship upgrades
        for upg, data in ship_upgrades.items():
            price = data["price"]
            gain = estimate_gain("shipupgrade", upg, ship)
            upgrades.append(("shipupgrade", upg, price, gain))
            
        # Trader upgrade
        price = station_upgrades["trader-upgrade"]
        gain = estimate_gain("trader", str(station["trader"]), station)
        upgrades.append(("trader", str(station["trader"]), price, gain))
        
        # New ship
        for ship_data in available:
            ship_id = ship_data["id"]
            price = ship_data["price"]+30000
            gain = estimate_gain("ship", ship_id, player)
            upgrades.append(("ship", ship_id, price, gain))
        
        # Trier par rentabilité
        upgrades.sort(key=lambda u: u[3] / u[2], reverse=True)
        
        # Seuil de ratio
        top_ratio = upgrades[0][3] / upgrades[0][2]
        min_ratio = top_ratio * (1.0 - 0.10)
        shipmoney = money / len(player["ships"])  # Money per ship
        moneyMinCap = shipmoney*0.1
        shipUpgradeCap = 100
        while upgrades:
            kind, id_, price, gain = upgrades[0]
            ratio = gain / price

            if ratio < min_ratio:
                logger.log(f"[] Skipping {kind} {id_}: ratio too low ({ratio:.4f}) price={price:.1f}, gain={gain:.1f})")
                upgrades.pop(0)  # Enlever de la liste
                continue

            if shipmoney <= price + moneyMinCap:
                logger.log(f"[] Not enough money for {kind} {id_}: need {price:.1f}, have {shipmoney:.1f}, gain={gain:.1f}%")
                upgrades.pop(0)
                continue

            try:
                if kind == "module":
                    res = self.get(f"/station/{self.sta}/shop/modules/{sid}/upgrade/{id_}")
                    logger.log(f"[] Module {id_} upgraded for {price:.1f} & gain {gain:.1f}%")
                elif kind == "crew":
                    res = self.get(f"/station/{self.sta}/crew/upgrade/ship/{sid}/{id_}")
                    logger.log(f"[] Crew {id_} upgraded for {price:.1f} & gain {gain:.1f}%")
                elif kind == "shipupgrade":
                    res = self.get(f"/station/{self.sta}/shipyard/upgrade/{sid}/{id_}")
                    logger.log(f"[] Ship upgrade {id_} for {price:.1f} & gain {gain:.1f}%")  
                    shipUpgradeCap -= 1
                    if shipUpgradeCap <= 0:
                        logger.log("[] Ship upgrades cap reached")
                        upgrades.pop(0)
                        continue
                elif kind == "trader":
                    res = self.get(f"/station/{self.sta}/crew/upgrade/trader")
                    logger.log(f"[] Trader upgraded for {price:.1f} & gain {gain:.1f}%")
                elif kind == "ship":
                    res = self.get(f"/station/{self.sta}/shipyard/buy/{id_}")
                    threading.Thread(target=self.ship_cycle, args=(self,id_), daemon=True).start()
                    logger.log(f"[] Bought new ship {id_} for {price:.1f} & gain {gain:.1f}%")
                shipmoney -= price
            except SimeisError as e:
                logger.log(f"[!] Upgrade {kind} {id_} failed:", e)
                upgrades.pop(0)
                continue
            
            ship = self.get(f"/ship/{sid}")

            if kind == "module":
                mod_preview = self.get(f"/station/{self.sta}/shop/modules/{sid}/upgrade")
                price = mod_preview[str(id_)]["price"]
                gain = estimate_gain("module", id_, ship)
            elif kind == "crew":
                crew_preview = self.get(f"/station/{self.sta}/crew/upgrade/ship/{sid}")
                price = crew_preview[str(id_)]["price"]
                gain = estimate_gain("crew", id_, ship)
            elif kind == "shipupgrade":
                gain = estimate_gain("shipupgrade", id_, ship)
            elif kind == "trader":
                station_upgrades = self.get(f"/station/{self.sta}/upgrades")
                price = station_upgrades["trader-upgrade"]
                gain = estimate_gain("trader", id_, station)

            upgrades[0] = (kind, id_, price, gain)
            upgrades.sort(key=lambda u: u[3] / u[2], reverse=True)

            top_ratio = upgrades[0][3] / upgrades[0][2]
            min_ratio = top_ratio * (1.0 - 0.10)
        logger.log(f"[*] Ship money left after upgrades: {shipmoney:.2f} credits")

    def upgrade_path_for_ship(self, sid, logger):
        logger.info(f"[*{sid}] Running centralized upgrade path with fallback")

        while True:
            ship = self.get(f"/ship/{sid}")
            crew = self.get(f"/station/{self.sta}/crew/upgrade/ship/{sid}")
            upgrades_available = self.get(f'/station/{self.sta}/shipyard/upgrade')
            player_status = self.get(f"/player/{self.pid}")
            player_money = player_status["money"]
            safety_threshold = player_status["costs"] * 600  # 10 minutes of survival buffer

            pilot_key, pilot = next(((k, v) for k, v in crew.items() if v.get('member-type') == 'Pilot'), (None, {}))
            operator_key, operator = next(((k, v) for k, v in crew.items() if v.get('member-type') == 'Operator'), (None, {}))
            modules = self.get(f'/station/{self.sta}/shop/modules/{sid}/upgrade')
            module_info = ship.get('modules', {}).get('1', {})

            upgraded = False

            for step in self.UPGRADE_PATH:
                if self.ready_for_next_step:
                    logger.info(f'[*{sid}] Skipping upgrades, stacking money for next ship.')
                    return

                step_threshold = player_status["costs"] * step.get("threshold_secs", 300)

                t = step["type"]
                if t == "trader" and self.number_of_trader_upgrades <= step["min_rank"]:
                    price = self.get(f"/station/{self.sta}/upgrades")["trader-upgrade"]
                    if player_money > price + step_threshold:
                        self.get(f"/station/{self.sta}/crew/upgrade/trader")
                        self.number_of_trader_upgrades += 1
                        logger.info(f"[*{sid}] Upgraded trader to level {self.number_of_trader_upgrades}")
                        upgraded = True
                        break

                elif t == "pilot" and pilot.get("rank", 0) <= step["min_rank"]:
                    price = pilot.get("price", 0)
                    if player_money > price + step_threshold:
                        self.get(f"/station/{self.sta}/crew/upgrade/ship/{sid}/{pilot_key}")
                        logger.info(f"[*{sid}] Upgraded pilot to rank {pilot['rank'] + 1}")
                        upgraded = True
                        break

                elif t == "operator" and operator.get("rank", 0) <= step["min_rank"]:
                    price = operator.get("price", 0)
                    if player_money > price + step_threshold:
                        self.get(f"/station/{self.sta}/crew/upgrade/ship/{sid}/{operator_key}")
                        logger.info(f"[*{sid}] Upgraded operator to rank {operator['rank'] + 1}")
                        upgraded = True
                        break

                elif t == "cargo" and ship["cargo"]["capacity"] <= step["min_capacity"]:
                    price = upgrades_available['CargoExpansion']['price']
                    if player_money > price + step_threshold:
                        self.get(f"/station/{self.sta}/shipyard/upgrade/{sid}/cargoexpansion")
                        logger.info(f"[*{sid}] Cargo upgrade bought")
                        upgraded = True
                        break

                elif t == "reactor" and ship["reactor_power"] <= step["min_power"]:
                    price = upgrades_available['ReactorUpgrade']['price']
                    if player_money > price + step_threshold:
                        self.get(f"/station/{self.sta}/shipyard/upgrade/{sid}/reactorupgrade")
                        logger.info(f"[*{sid}] Reactor upgrade bought")
                        upgraded = True
                        break

                elif t == "module" and module_info.get("rank", 0) <= step["min_rank"]:
                    mod_price = modules.get('1', {}).get("price")
                    if mod_price and player_money > mod_price + step_threshold:
                        self.get(f'/station/{self.sta}/shop/modules/{sid}/upgrade/1')
                        logger.info(f"[*{sid}] Upgraded module to rank {module_info['rank'] + 1}")
                        upgraded = True
                        break

            if upgraded:
                continue  # Recheck everything

            if self.ready_for_next_step:
                    logger.info(f'[*{sid}] Skipping upgrades, stacking money for next ship.')
                    return
            
            # Fallback: expand cargo up to 50000 if money allows
            if ship["cargo"]["capacity"] < 50000:
                fallback_price = upgrades_available['CargoExpansion']['price']
                if player_money > fallback_price + safety_threshold:
                    self.get(f"/station/{self.sta}/shipyard/upgrade/{sid}/cargoexpansion")
                    logger.info(f"[*{sid}] Fallback: Cargo upgrade to capacity {ship['cargo']['capacity'] + 100}")
                    continue  # Recheck upgrades
                else:
                    logger.info(f"[*{sid}] Fallback cargo upgrade skipped (not enough money)")
            else:
                logger.info(f"[*{sid}] Fallback: cargo at max threshold (50000)")

            # Fallback: operator level
            if  operator.get("rank", 0) <= 35:
                price = operator.get("price", 0)
                if player_money > price + step_threshold:
                    self.get(f"/station/{self.sta}/crew/upgrade/ship/{sid}/{operator_key}")
                    logger.info(f"[*{sid}] Upgraded operator to rank {operator['rank'] + 1}")
                    continue 

            break


    def check_for_next_ship(self,logger):
        
        
        statsDesired = {'cargo capacity': 1500,
                        'Reactor power' : 10,
                        'Operator rank' :  9,
                        'Pilot rank'    : 1,
                        #'Trader rank'   : 1
                        }
        

        ship_ok_count = 0

        
        
        for sid in self.sid:
            ship = self.get(f"/ship/{sid}")
            crew = ship['crew']
            
            pilot = next((v for v in crew.values() if v.get('member_type') == 'Pilot'), None)
            operator = next((v for v in crew.values() if v.get('member_type') == 'Operator'), None)

            
            currentStats = {
                'cargo capacity': ship["cargo"]["capacity"],
                'Reactor power': ship["reactor_power"],
                'Operator rank': operator['rank'] if operator else 0,
                'Pilot rank': pilot['rank'] if pilot else 0,
                #'Trader rank'   : self.number_of_trader_upgrades

            }

            logger.info(f'[*] Desired stats to keep on with expansion plan:{statsDesired}')
            logger.info(f'[*{sid}] CurrentStats : {currentStats}')
        

            if all(currentStats.get(k, 0) >= v for k, v in statsDesired.items()):
                ship_ok_count += 1
            else:
                logger.info(f"[*{sid}] Ship {sid} does not meet desired stats: {currentStats}")

        if ship_ok_count == len(self.sid):
            logger.info("[*] All ships meet desired stats. Stacking money.")
            self.ready_for_next_step = True

        if self.get_player_money()>400000 :
            logger.info("[*] Enough money stacked even tho ships don't meet requirements")
            self.ready_for_next_step = True


    

        
        
    def build_station_panel(self,station):
        table = Table.grid()
        table.add_row("[bold cyan]Station ID[/bold cyan]", str(station['id']))
        table.add_row("[bold cyan]Position[/bold cyan]", str(station['position']))
        table.add_row("[bold cyan]Cargo[/bold cyan]", f"{station['cargo']['usage']} / {station['cargo']['capacity']}")
        table.add_row("[bold cyan]Trader[/bold cyan]", f"{station['crew']}")

        for res, amt in station['cargo']['resources'].items():
            table.add_row(f"  {res}", str(amt))
        
        return Panel(table, title="STATION", border_style="cyan",width=panel_width)


    def build_ship_panel(self,index, ship):
        table = Table.grid()
        table.add_row("[bold magenta]État[/bold magenta]", str(ship.get('state')))
        table.add_row("Position", str(ship.get('position')))
        table.add_row("Fuel", f"{ship.get('fuel_tank')} / {ship.get('fuel_tank_capacity')}")
        table.add_row("Hull", f"{ship['hull_decay_capacity'] - ship['hull_decay']} / {ship['hull_decay_capacity']}")
        table.add_row("Reactor", f"{ship.get('reactor_power')} for {ship['stats']['speed']}")
        table.add_row("Cargo", f"{ship['cargo']['usage']} / {ship['cargo']['capacity']}")

        for module in ship.get('modules', {}).values():
            table.add_row("Module", str(module))

        for member in ship.get('crew', {}).values():
            table.add_row("Crew", f"{member['member_type']} (rank {member['rank']})")

        for res, amt in ship['cargo']['resources'].items():
            table.add_row(f"  {res}", str(amt))

        return Panel(table, title=f"SHIP {index}", border_style="red",width=panel_width)

    def build_player_panel(self):
        status = game.get("/player/" + str(self.pid))
        money = round(status["money"], 2)
        tbd =  int(status["money"] / status["costs"])
        num_ships = len(self.sid)
        cost_per_sec = round(status["costs"], 2)
        
        time_played_fmt = str(datetime.now()-self.startTime).split('.')[0]  # Removes microseconds


        table = Table.grid()
        table.add_row("[bold yellow]Money : [/bold yellow]", f"{money:,.2f} ¤")
        table.add_row("Time Before Death : ", str(tbd))
        table.add_row("Number of Ships : ", str(num_ships))
        table.add_row("Costs per second : ", f"{cost_per_sec:,.2f} ¤/s")
        table.add_row("Time Played", time_played_fmt)

        return Panel(table, title=f"PLAYER {status["name"]}", border_style="yellow",width=panel_width)

    def display_dashboard(self):
        with Live(refresh_per_second=3, screen=True) as live:
            while True:
                try:
                    station = self.get(f'/station/{self.sta}')
                    ships = []
                    for sid in self.sid[:2]:
                        try:
                            ship = self.get(f"/ship/{sid}")
                            ships.append(ship)
                        except Exception as e:
                            ships.append({"state": f"Erreur récupération: {e}"})
                except Exception as e:
                    live.update(Panel(f"[bold red]Erreur récupération des données: {e}[/bold red]"))
                    time.sleep(2)
                    continue

                panels = [self.build_player_panel(),self.build_station_panel(station)]
                for index, ship in enumerate(ships, start=1):
                    panels.append(self.build_ship_panel(index, ship))

                layout = Table.grid(padding=1)
                for panel in panels:
                    layout.add_row(panel)

                live.update(layout)
                time.sleep(0.3)


    def expand_station_storage_if_needed_by_volume(self, sid, logger):
        ship = self.get(f"/ship/{sid}")
        station = self.get(f"/station/{self.sta}")

        # Total à vendre
        total_to_unload = ship["cargo"]["capacity"]
        capacity = station["cargo"]["capacity"]

        # Combien de déchargements seraient nécessaires ?
        required_unloads = (total_to_unload + capacity - 1) // capacity

        if required_unloads <= 3:
            return  # Pas besoin d'élargir

        # Cible : tout vendre en 3 déchargements max
        target_capacity = (total_to_unload + 2) // 3
        extra_space_needed = target_capacity - capacity

        station_upgrades = self.get(f'/station/{self.sta}/upgrades')
        logger.info(station_upgrades)
        cost_per_unit = station_upgrades["cargo-expansion"]  # fictif, à ajuster selon ton jeu
        total_cost = extra_space_needed * cost_per_unit
        player = self.get(f"/player/{self.pid}")
        safety_threshold = player["costs"] * 300
        
        if player["money"] > total_cost + safety_threshold:
            self.get(f"/station/{self.sta}/shop/cargo/buy/{int(extra_space_needed)}")  # Endpoint fictif
            logger.info(f"[*{sid}] Achat de {extra_space_needed} stockage pour tout vendre en 3 déchargements")

        else:

            logger.info(f"[*{sid}] Pas assez de crédits pour acheter {int(extra_space_needed)} stockage supplémentaire")

    # - Go back to the station
    # - Unload all the cargo
    # - Sell it on the market
    # - Refuel & repair the ship
    def go_sell(self,sid,logger):
        self.wait_idle(sid) # If we are currently occupied, wait
        ship = self.get(f"/ship/{sid}")
        station = self.get(f"/station/{self.sta}")

        # If we aren't at the station, got there
        if ship["position"] != station["position"]:
            self.travel(ship["id"], station["position"],logger)
        sold_total = 0

        
        

        self.expand_station_storage_if_needed_by_volume(sid,logger)
        # Unload the cargo and sell it directly on the market
        while True:
            ship = self.get(f"/ship/{sid}")
            #logger.info(f'[*{sid}] AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA')
            resources = ship["cargo"]["resources"]
            if all(amount == 0 for amount in resources.values()):
                break
            for res, amt in resources.items():
                if amt > 0:
                    unloaded = self.get(f"/ship/{sid}/unload/{res}/{amt}")
                    sold = self.get(f"/market/{self.sta}/sell/{res}/{amt}")
                    logger.info("[*{}] Unloaded and sold {} of {}, for {} credits".format(sid,unloaded["unloaded"], res, sold["added_money"]))
                    sold_total += sold["added_money"]
            time.sleep(1)

        logger.info(f"[*{sid}] ALL RESSOURCES SOLD for a total of {sold_total} credits")
        print(f"[*{sid}] ALL RESSOURCES SOLD for a total of {sold_total} credits")

        if self.should_do_repairs(sid,logger):
            self.ship_repair(sid,logger)
        self.ship_refuel(sid,logger)
    
    def ship_cycle(self, sid,logger):
        try:
            ship_concerned = self.get(f'/ship/{sid}')
            logger.info(f"[*] Ship {ship_concerned} cycle began")
            self.go_mine(sid,logger)
            self.go_sell(sid,logger)
            self.optimize_upgrades(sid,logger)
            
        except Exception as e:
            logger.info(f"[!] Error during ship {sid} cycle: {e}")


if __name__ == "__main__":
    name = sys.argv[1]
    game = Game(name)
    game.init_game()
    launched_ships = set()
    lock = threading.Lock()

    def continuous_ship_loop(sid,index):
            playerName = game.get(f"/player/{game.pid}")['name']
            thread_name = f"{playerName}-Ship-{index}"
            logger = get_thread_logger(thread_name)
            while True:
                try:
                    game.ship_cycle(sid,logger)
                    logger.info('Completed a cycle')
                except Exception as e:
                    logger.error(f"[Ship {sid}] Error: {e}")
                time.sleep(0.5)

    def check_and_buy_loop():
        playerName = game.get(f"/player/{game.pid}")['name']
        thread_name = f"{playerName}-CheckBuyThread"
        logger = get_thread_logger(thread_name)
        while True:
            try:
                game.check_for_next_ship(logger)
                game.buy_new_ship_if_ready(logger)
                logger.info("Checked and bought ship if ready")
                current_ships = game.sid
                with lock:
                    for index,sid in enumerate(current_ships):
                        if sid not in launched_ships:
                            logger.info(f'Lauching new thread for ship {sid}')
                            t = threading.Thread(target=continuous_ship_loop, args=(sid, index), daemon=True, name=f"ShipThread-{index}")
                            t.start()
                            launched_ships.add(sid)
            except Exception as e:
                logger.error(f"[Check/Buy] Error: {e}")
            time.sleep(15)

    
    def get_thread_logger(thread_name):
            
            os.makedirs("logs", exist_ok=True)


            logger = logging.getLogger(thread_name)
            logger.setLevel(logging.INFO)
            
            # Avoid adding multiple handlers if logger already has handlers
            if not logger.hasHandlers():
                handler = logging.FileHandler(f'logs/{thread_name}.log', mode='a')
                formatter = logging.Formatter('%(asctime)s %(levelname)s: %(message)s')
                handler.setFormatter(formatter)
                logger.addHandler(handler)
            return logger

    def run_dashboard_loop(game):
        while True:
            game.display_dashboard()
            time.sleep(0.1)

    for index, sid in enumerate(game.sid):
            t = threading.Thread(target=continuous_ship_loop, args=(sid, index), daemon=True, name=f"ShipThread-{index}")
            t.start()
            launched_ships.add(sid)

    print('coucou')    
    print('Recoucou')
    print(f"[*] Starting threads for {len(game.sid)} ships")

    threading.Thread(target=run_dashboard_loop,args=(game,),daemon=True,name="Dashboard").start()

    threading.Thread(target=check_and_buy_loop, daemon=True, name="CheckBuyThread").start()

    while True:
        time.sleep(10)  # keep main thread alive


