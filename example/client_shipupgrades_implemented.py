PORT=8080
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
        self.number_of_trader_upgrades = 0
        self.last_hullplate_values = []
        self.flips = {}
        self.ready_for_next_step = None
        self.second_ship_bought = False

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
    
    def get_player_money(self):
        return self.get(f"/player/{self.pid}")["money"]

    def upgrade_trader_if_enough_money(self,sid,logger):
        if self.ready_for_next_step:
            logger.info(f'[*{sid}] No upgrading, stacking money for next step')
            return
        
        logger.info(f"[*{sid}] Level of the trader: {self.number_of_trader_upgrades}")

        trader_upgrade_price = self.get(f"/station/{self.sta}/upgrades")["trader-upgrade"]
        player_money = self.get_player_money()
        required_money = [trader_upgrade_price + 600, trader_upgrade_price + 2500, trader_upgrade_price + 4000]

        if self.number_of_trader_upgrades>=1 :
            logger.info(f'[*{sid}] Trader already at desired level -- No upgrades bought')
            return
        
        if self.number_of_trader_upgrades < len(required_money) and player_money > required_money[self.number_of_trader_upgrades]:
            self.get(f"/station/{self.sta}/crew/upgrade/trader")
            logger.info(f"[*{sid}] Trader upgrade level {self.number_of_trader_upgrades + 1} bought")
            self.number_of_trader_upgrades += 1
        else:
            logger.info(f"[*{sid}] The trader upgrade was too expensive for us")


    def upgrade_single_operator_if_possible(self,sid,logger):
        #logger.info(f'[LOGS] ready? operator: {self.ready_for_next_step}')

        if self.ready_for_next_step:
            logger.info(f'[*{sid}] No upgrading, stacking money for next step')
            return
        
        
        actual_crew_augment = self.get(f"/station/{self.sta}/crew/upgrade/ship/{sid}")
        logger.info(f"[*{sid}] Available crew augments: {actual_crew_augment}")

        pilot = next((v for v in actual_crew_augment.values() if v.get('member-type') == 'Pilot'), None)
        operator_key, operator = next(((k, v) for k, v in actual_crew_augment.items() if v.get('member-type') == 'Operator'), (None, None))

        if not pilot or not operator:
            logger.info("[!] Could not find Pilot or Operator")
            return

        if pilot["rank"] < 2 and operator["rank"] > 2:
            logger.info(f"[*{sid}] Must rank up Pilot before further operator upgrades\n")
            return

        if operator['rank']>=30:
            logger.info(f'[*{sid}] Operator at max level')
            return
        
        operator_price = operator["price"]
        rank_thresholds = {
            2: 800,
            3: 1000,
            4: 1500,
            5: 2000
        }

        player_money = self.get_player_money()
        rank = operator["rank"]
        logger.info(f'[LOGS] rank : {rank}')

        logger.info(f'[LOGS] operator price : {operator_price}')
        

        if rank >= 5 :
            threshold = 2000
        else:
            threshold = rank_thresholds.get(rank)

        logger.info(f'[LOGS] threshold : {threshold}')


        if (operator_price + threshold) < player_money:
            self.get(f"/station/{self.sta}/crew/upgrade/ship/{sid}/{operator_key}")
            logger.info(f"[*{sid}] Upgrade for Operator bought\n")
        else:
            logger.info(f"[*{sid}] The operator upgrade was too expensive for us (or rank already too high)\n")


    def upgrade_single_pilot_if_possible(self,sid,logger):
        #logger.info(f'[LOGS] ready? pilot: {self.ready_for_next_step}')

        if self.ready_for_next_step:
            logger.info(f'[*{sid}] No upgrading, stacking money for next step')
            return


        
        actual_crew_augment = self.get(f"/station/{self.sta}/crew/upgrade/ship/{sid}")
        logger.info(f"[*{sid}] Available crew augments: {actual_crew_augment}")

        pilot_key, pilot = next(((k, v) for k, v in actual_crew_augment.items() if v.get('member-type') == 'Pilot'), (None, None))
        if not pilot:
            logger.info("[!] Could not find Pilot\n")
            return
        
        if pilot['rank'] >=3 :
            logger.info(f'[*{sid}] Pilot at max level')
            return
        
        player_money = self.get_player_money()
        upgrade_thresholds = {
            2: 1000,
            3: 4000,
        }

        rank = pilot["rank"]
        if rank >= 4 :
            threshold = 2000000
        else:
            threshold = upgrade_thresholds.get(rank)

        if threshold and (pilot["price"] + threshold) < player_money:
            self.get(f"/station/{self.sta}/crew/upgrade/ship/{sid}/{pilot_key}")
            logger.info(f"[*{sid}] Upgrade for Pilot bought\n")
        else:
            logger.info(f"[*{sid}] The pilot upgrade was too expensive for us (or rank already too high)\n")


    def upgrade_ship(self,sid,logger):
        #logger.info(f'[LOGS] ready? ship : {self.ready_for_next_step}')

        if self.ready_for_next_step:
            logger.info(f'[*{sid}] No upgrading, stacking money for next step')
            return

        if sid not in self.flips:
            self.flips[sid] = 0

        logger.info(f"[*{sid}] Checking for ship upgrades")

        player_money = self.get_player_money()
        upgrades_available = self.get(f'/station/{self.sta}/shipyard/upgrade')
        actual_crew = self.get(f"/station/{self.sta}/crew/upgrade/ship/{sid}")
        ship = self.get(f'/ship/{sid}')

        pilot = next((v for v in actual_crew.values() if v.get('member-type') == 'Pilot'), {})
        operator = next((v for v in actual_crew.values() if v.get('member-type') == 'Operator'), {})
        flip = self.flips[sid]

        logger.info(f"[*{sid}] Current ship cargo capacity: {ship['cargo']['capacity']}")
        logger.info(f"[*{sid}] Current ship reactor power: {ship['reactor_power']}")
        logger.info(f"[LOGS] flip value = {self.flips[sid]}")
        logger.info(f"[*{sid}] Upgrades available: {upgrades_available}")

        if ship["reactor_power"] >=15 :
            flip = 0

        
        if flip == 0:
            logger.info(f"[*{sid}] Considering cargo expansion upgrade...")
            price = upgrades_available['CargoExpansion']['price']
            if (ship["cargo"]["capacity"] <= 400 and player_money > 600 + price) or (pilot.get("rank", 0) >= 3 and operator.get("rank", 0) >= 3 and player_money > 1500 + price):
                self.get(f'/station/{self.sta}/shipyard/upgrade/{sid}/cargoexpansion')
                self.flips[sid] = 1
                logger.info(f"[*{sid}] Cargo expansion upgrade bought")
                logger.info(f"[LOGS] flip value = {self.flips[sid]}")
            else:
                logger.info(f"[*{sid}] Cargo expansion upgrade too expensive or not in priority list")
        elif flip == 1:
            logger.info(f"[*{sid}] Considering reactor upgrade...")
            price = upgrades_available['ReactorUpgrade']['price']
            if (ship["reactor_power"] < 2 and player_money > 800 + price) or (pilot.get("rank", 0) >= 3 and operator.get("rank", 0) >= 3 and player_money > 1500 + price):
                self.get(f'/station/{self.sta}/shipyard/upgrade/{sid}/reactorupgrade')
                self.flips[sid] = 0
                logger.info(f"[*{sid}] Reactor upgrade bought")
                logger.info(f"[LOGS] flip value = {self.flips[sid]}")
            else:
                logger.info(f"[*{sid}] Reactor upgrade too expensive or not in priority list")
        else :
            logger.info(f"[*{sid}] No ship upgrades considered, stacking money for further improvements")
        logger.info("")


    def check_for_next_ship(self,logger):
        
        
        statsDesired = {'cargo capacity': 1500,
                        'Reactor power' : 10,
                        'Operator rank' :  15,
                        'Pilot rank'    : 2,
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
        if self.should_do_repairs(sid,logger):
            self.ship_repair(sid,logger)
        self.ship_refuel(sid,logger)
    
    def ship_cycle(self, sid,logger):
        try:
            print('InsideCycle')
            ship_concerned = self.get(f'/ship/{sid}')
            logger.info(f"[*] Ship {ship_concerned} cycle began")
            self.disp_status()
            self.go_mine(sid,logger)
            self.disp_market()
            self.go_sell(sid,logger)
            #self.upgrade_trader_if_enough_money()
            self.upgrade_ship(sid,logger)
            self.upgrade_single_pilot_if_possible(sid,logger)
            self.upgrade_single_operator_if_possible(sid,logger)
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

    for index, sid in enumerate(game.sid):
            t = threading.Thread(target=continuous_ship_loop, args=(sid, index), daemon=True, name=f"ShipThread-{index}")
            t.start()
            launched_ships.add(sid)

            print("Hello")
        
    print(f"[*] Starting threads for {len(game.sid)} ships")

    

    threading.Thread(target=check_and_buy_loop, daemon=True, name="CheckBuyThread").start()

    while True:
        time.sleep(10)  # keep main thread alive


