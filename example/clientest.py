PORT = 8080
URL = f"http://127.0.0.1:{PORT}"

import os, sys, math, time, json, string, urllib.request

class SimeisError(Exception): pass

def get_dist(a, b):
    return math.sqrt(sum((a[i] - b[i]) ** 2 for i in range(3)))

def check_has(alld, key, *req):
    alltypes = [c[key] for c in alld.values()]
    return all([k in alltypes for k in req])

class Game:
    def __init__(self, username):
        assert self.get("/ping")["ping"] == "pong"
        print("[*] Connection to server OK")
        self.setup_player(username)
        self.pid = self.player["playerId"]
        self.sid = None
        self.sta = None
        self.last_prices = {}
        self.sell_cooldown = 0

    def get(self, path, **qry):
        if hasattr(self, "player"):
            qry["key"] = self.player["key"]
        tail = "?" + "&".join([f"{k}={urllib.parse.quote(str(v))}" for k, v in qry.items()]) if qry else ""
        data = json.loads(urllib.request.urlopen(f"{URL}{path}{tail}", timeout=2).read().decode())
        if data.pop("error") != "ok":
            raise SimeisError(data.get("error", "Unknown"))
        return data

    def disp_status(self):
        status = self.get("/player/" + str(self.pid))
        money = round(status["money"], 2)
        costs = round(status["costs"], 2)
        secs = int(status["money"] / status["costs"]) if costs > 0 else 99999
        print(f"[*] Current status: {money} credits, costs: {costs}, time left before lost: {secs} secs")

    def setup_player(self, username, force_register=False):
        username = ''.join(c for c in username if c.isalnum()).lower()
        if force_register or not os.path.exists(f"./{username}.json"):
            self.player = self.get(f"/player/new/{username}")
            with open(f"./{username}.json", "w") as f:
                json.dump(self.player, f)
            print(f"[*] Created player {username}")
        else:
            with open(f"./{username}.json") as f:
                self.player = json.load(f)
            print(f"[*] Loaded data for player {username}")

        try:
            player = self.get(f"/player/{self.player['playerId']}")
        except SimeisError:
            return self.setup_player(username, force_register=True)

        if player["money"] <= 0.0:
            print("!!! Player already lost, please restart the server to reset the game")
            sys.exit(0)

    def wait_idle(self):
        ship = self.get(f"/ship/{self.sid}")
        while ship["state"] != "Idle":
            time.sleep(1)
            ship = self.get(f"/ship/{self.sid}")

    def init_game(self):
        status = self.get(f"/player/{self.pid}")
        self.sta = list(status["stations"].keys())[0]
        station = self.get(f"/station/{self.sta}")
        if not check_has(station["crew"], "member_type", "Trader"):
            trader = self.get(f"/station/{self.sta}/crew/hire/trader")["id"]
            self.get(f"/station/{self.sta}/crew/assign/{trader}/trading")
        if not status["ships"]:
            self.buy_ship()
            status = self.get(f"/player/{self.pid}")
        self.sid = status["ships"][0]["id"]
        if not check_has(status["ships"][0]["crew"], "member_type", "Pilot"):
            pilot = self.get(f"/station/{self.sta}/crew/hire/pilot")["id"]
            self.get(f"/station/{self.sta}/crew/assign/{pilot}/{self.sid}/pilot")
        print("[*] Game initialisation finished successfully")

    def buy_ship(self):
        ships = self.get(f"/station/{self.sta}/shipyard/list")["ships"]
        cheapest = sorted(ships, key=lambda s: s["price"])[0]
        self.get(f"/station/{self.sta}/shipyard/buy/{cheapest['id']}")

    def get_best_planet(self):
        planets = self.get(f"/station/{self.sta}/scan")["planets"]
        market = self.get("/market/prices")["prices"]
        station = self.get(f"/station/{self.sta}")
        def estimated_profit(planet):
            mod = "Miner" if planet["solid"] else "GasSucker"
            price = market.get("Iron" if mod == "Miner" else "Helium", 0)
            difficulty = 1.0 if mod == "Miner" else 0.8
            return price / difficulty / get_dist(station["position"], planet["position"])
        return sorted(planets, key=estimated_profit, reverse=True)[0]

    def go_mine(self):
        best = self.get_best_planet()
        ship = self.get(f"/ship/{self.sid}")
        modtype = "Miner" if best["solid"] else "GasSucker"
        if not check_has(ship["modules"], "modtype", modtype):
            mod = self.get(f"/station/{self.sta}/shop/modules/{self.sid}/buy/{modtype}")["id"]
            if not check_has(ship["crew"], "member_type", "Operator"):
                op = self.get(f"/station/{self.sta}/crew/hire/operator")["id"]
                self.get(f"/station/{self.sta}/crew/assign/{op}/{self.sid}/{mod}")
        if ship["position"] != best["position"]:
            self.get(f"/ship/{self.sid}/navigate/{'/'.join(map(str, best['position']))}")
            self.wait_idle()
        self.get(f"/ship/{self.sid}/extraction/start")
        self.wait_idle()

    def go_sell(self):
        self.wait_idle()
        ship = self.get(f"/ship/{self.sid}")
        station = self.get(f"/station/{self.sta}")
        if ship["position"] != station["position"]:
            self.get(f"/ship/{self.sid}/navigate/{'/'.join(map(str, station['position']))}")
            self.wait_idle()
        prices = self.get("/market/prices")["prices"]
        for res, amt in ship["cargo"]["resources"].items():
            if amt == 0.0: continue
            price = prices[res]
            if res not in self.last_prices:
                self.last_prices[res] = price
            if price >= 0.85 * self.last_prices[res] or self.sell_cooldown >= 3:
                self.get(f"/ship/{self.sid}/unload/{res}/{amt}")
                self.get(f"/market/{self.sta}/sell/{res}/{amt}")
                print(f"[*] Sold {amt} of {res} at {price:.2f} credits/unit")
                self.last_prices[res] = price
                self.sell_cooldown = 0
            else:
                print(f"[~] Holding {res}: {price:.2f} < {0.85 * self.last_prices[res]:.2f}")
                self.sell_cooldown += 1

    def should_enter_safe_mode(self):
        status = self.get(f"/player/{self.pid}")
        return status["money"] / status["costs"] < 300

if __name__ == "__main__":
    name = sys.argv[1]
    game = Game(name)
    game.init_game()

    while True:
        print("\n[*] === GAME CYCLE START ===")
        game.disp_status()
        if game.should_enter_safe_mode():
            print("[!] Activating SAFE MODE (low balance)")
            game.go_sell()
        else:
            game.go_mine()
            game.go_sell()
        time.sleep(1)
