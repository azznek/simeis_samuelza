PORT=8080
URL=f"http://127.0.0.1:{PORT}"

import os
import json
import time
import urllib.request
from datetime import datetime
# TODO HTTP server that serves a graph of the data

INIT = False
HIST = {}

class SimeisError(Exception):
    pass

NMAX=30
WIDTH=100
SCORE="█"
POTENTIAL="▒"
VOID=" "
LAUNCHTIME = datetime.now()

MIN = {}
MAX = {}

def mkbar(score, pot, maxs):
    if maxs == 0.0:
        ps = 0
        pp = 0
    else:
        ps = score / maxs
        pp = pot / maxs
    nbs = int(WIDTH * ps)
    nbp = int(WIDTH * pp)
    nvoid = WIDTH - nbs - nbp
    return (SCORE * nbs) + (POTENTIAL * nbp) + (VOID * nvoid)

def get(path):
    qry = f"{URL}/{path}"
    while True:
        try:
            reply = urllib.request.urlopen(qry, timeout=5)
            break
        except:
            os.system('cls' if os.name == 'nt' else 'clear')
            HIST = {}
            INIT=False
            breakpoint()
            # print("DEAD SERVER")
            # time.sleep(1)
            continue

    data = json.loads(reply.read().decode())
    err = data.pop("error")
    if err != "ok":
        raise SimeisError(err)

    return data

def get_info():
    return get("gamestats")

def get_resources():
    return get("resources")

def get_market():
    return get("market/prices")["prices"]

def disp_market(resources):
    market = get_market()
    max_res_len = max([len(k) for k in market.keys()])
    disp = {}
    for (res, price) in market.items():
        MIN[res] = round(min(MIN[res], price), 2)
        MAX[res] = round(max(MAX[res], price), 2)
        relp = round((price / resources[res]["base-price"]) * 100, 2)
        price = round(price, 3)
        space = " "*(1 + max_res_len - len(res))

        disp[res] = {
            "head": f"{price}",
            "mid": f"({relp} %)",
            "tail": "({} < {} < {})".format(MIN[res], resources[res]["base-price"], MAX[res]),
        }

    max_res = max([len(r) for r in disp.keys()])
    max_head = max([len(d["head"]) for _, d in disp.items()])
    max_mid = max([len(d["mid"]) for _, d in disp.items()])
    max_tail = max([len(d["tail"]) for _, d in disp.items()])

    for res, d in disp.items():
        print("{}{}{}{}{}{}{}".format(
            res, " " * (max_res + 1 - len(res)),
            d["head"], " " * (max_head + 1 - len(d["head"])),
            d["mid"], " " * (max_mid + 1 - len(d["mid"])),
            d["tail"], " " * (max_tail + 1 - len(d["tail"])),
        ))

resources = get_resources()
for (res, data) in resources.items():
    MIN[res] = data["base-price"]
    MAX[res] = data["base-price"]

while True:
    time.sleep(2)
    os.system('cls' if os.name == 'nt' else 'clear')
    disp_market(resources)
    print("")
    print(f'Time elapsed since start of monitoring : {datetime.now() - LAUNCHTIME}')
    print("")
    info = get_info()
    if len(info) == 0:
        print("No players on the server")
        continue

    for (_, p) in info.items():
        if p["lost"]:
            p["score"] = -1.0

    players = sorted(info.items(), key=lambda p: p[1]["score"] + p[1]["potential"], reverse=True)[:NMAX]
    max_score = max([max(v["score"], 0) + v["potential"] for v in info.values()])
    for (player, data) in players:
        if player not in HIST:
            HIST[player] = []

        if data["lost"]:
            print("Player {}:\tLOST".format(data["name"]))
            continue

        s = max(0, data["score"]) + data["potential"]
        if data["age"] == 0:
            avg = 0.0
        else:
            avg = s / data["age"]
        HIST[player].append((s, avg))
        avg_lasts = max([n[1] for n in HIST[player][-30:]])

        bar = mkbar(data["score"], data["potential"], max_score)
        print("Player {}:\t{} {} (~{}/sec)\tpotential: {}".format(
            data["name"], bar, round(data["score"], 2),
            round(avg_lasts, 2),
            round(data["potential"], 2)
        ))
