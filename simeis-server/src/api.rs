use std::collections::BTreeMap;
use std::ops::{Deref, DerefMut};
use std::str::FromStr;
use std::time::Instant;

use base64::{prelude::BASE64_STANDARD, Engine};
use ntex::web::types::Path;
use ntex::web::{self, HttpRequest, HttpResponse, ServiceConfig};
use rand::Rng;
use serde_json::{json, to_value, Value};
use simeis_data::crew::{CrewId, CrewMember, CrewMemberType};
use simeis_data::galaxy::station::StationId;
use simeis_data::galaxy::SpaceUnit;
use simeis_data::market::fee_rate;
use simeis_data::player::{PlayerId, PlayerKey};
use simeis_data::ship::module::{ShipModuleId, ShipModuleType};
use simeis_data::ship::resources::Resource;
use simeis_data::ship::upgrade::ShipUpgrade;
use simeis_data::ship::{Ship, ShipId};
use simeis_data::syslog::SyslogEvent;
use strum::IntoEnumIterator;

pub type ApiResult = Result<Value, Errcode>;

use simeis_data::errors::Errcode;

use crate::GameState;

// TODO Use POST queries also, instead of everything with GET

// TODO (#35) Use query parameters (with ntex::web::types::Query) instead of plain URLs

macro_rules! get_player {
    ($srv:ident, $req:ident) => {{
        let Some(key) = get_player_key(&$req) else {
            return build_response(Err(Errcode::NoPlayerKey));
        };
        let index = $srv.player_index.read().await;
        let Some(id) = index.get(&key) else {
            return build_response(Err(Errcode::NoPlayerWithKey));
        };
        let players = $srv.players.read().await;
        let player = players.get(id).unwrap();
        if player.read().await.lost {
            return build_response(Err(Errcode::PlayerLost));
        }
        player.clone()
    }};
}

macro_rules! get_station {
    ($srv:expr, $player:expr, $id:expr) => {{
        let player = $player.read().await;
        let Some(station_coord) = player.stations.get($id).cloned() else {
            return build_response(Err(Errcode::NoSuchStation(*$id)));
        };
        drop(player);
        $srv.galaxy
            .read()
            .await
            .get_station(&station_coord)
            .await
            .unwrap()
    }};

    ($srv:expr, $id:expr; $player:expr) => {{
        let Some(station_coord) = $player.stations.get($id).cloned() else {
            return build_response(Err(Errcode::NoSuchStation(*$id)));
        };
        $srv.galaxy
            .read()
            .await
            .get_station(&station_coord)
            .await
            .unwrap()
    }};

    ($srv:expr, $id:expr; $player:expr; $galaxy:expr) => {{
        let Some(station_coord) = $player.stations.get($id).cloned() else {
            return build_response(Err(Errcode::NoSuchStation(*$id)));
        };
        $galaxy.get_station(&station_coord).await.unwrap()
    }};
}

// TODO    Ensure that multiple players cannot lock themselves:
//     Ask for write on X, wait for read on Y
//     Ask for write on Y, wait for read on X

// TODO    Centralise every read / write in the API
//     and give them a specific order:
//         player first, station after, galaxy then, etc...
// - Player index
// - Player list
// - Player
// - Galaxy
// - Station
// - Market
// - SyslogFifo
// - PlayerFifo

fn get_player_key(req: &HttpRequest) -> Option<PlayerKey> {
    for q in req.query_string().split("&") {
        if q.starts_with("key=") {
            let key = q.split("=").nth(1)?;
            let deckey = urlencoding::decode(key).ok()?;
            let mut key = [0; 128];
            BASE64_STANDARD
                .decode_slice(deckey.as_ref(), &mut key)
                .ok()?;
            return Some(key);
        }
    }
    None
}

pub fn jsonmerge(a: &mut Value, b: &Value) {
    match (a, b) {
        (Value::Object(a), Value::Object(b)) => {
            for (k, v) in b {
                jsonmerge(a.entry(k.clone()).or_insert(Value::Null), v);
            }
        }
        (a, b) => *a = b.clone(),
    }
}

fn build_response(res: ApiResult) -> HttpResponse {
    let body = match res {
        Ok(mut data) => {
            jsonmerge(&mut data, &json!({"error": "ok"}));
            data
        }
        Err(e) => {
            json!({"error": e.errmsg(), "type": format!("{e:?}")})
        }
    };

    HttpResponse::Ok()
        .content_type("application/json")
        .json(&body)
}

// CHECKED
#[web::get("/ping")]
async fn ping() -> impl web::Responder {
    build_response(Ok(json!({"ping": "pong"})))
}

// CHECKED
#[web::get("/syslogs")]
async fn get_syslogs(srv: GameState, req: HttpRequest) -> impl web::Responder {
    let player = get_player!(srv, req);
    let pid = player.read().await.id;
    let allfifo = srv.fifo_events.read().await;
    let Some(fifo) = allfifo.get(&pid) else {
        return build_response(Ok(json!({"nb": 0, "events": []})));
    };
    let fifo = fifo.clone();
    drop(allfifo);
    let mut fifo = fifo.write().await;
    let all_ev = fifo.remove_all();
    let res = all_ev
        .into_iter()
        .map(|(t, ev)| {
            let s: &'static str = ev.clone().into();
            json!({
                "timestamp": srv.tstart + t,
                "type": s,
                "event": ev,
            })
        })
        .collect::<Vec<Value>>();
    build_response(Ok(json!({ "nb": res.len(), "events": res, })))
}

// CHECKED
#[web::get("/player/new/{name}")]
async fn new_player(srv: GameState, name: Path<String>) -> impl web::Responder {
    let name = name.to_string();
    let players = srv.players.read().await;
    let all_players = players.keys().collect::<Vec<&PlayerId>>();
    for pid in all_players {
        let player = players.get(pid).unwrap();
        if name == player.read().await.name {
            return build_response(Err(Errcode::PlayerAlreadyExists(*pid, name)));
        }
    }
    drop(players);

    let res = srv.new_player(name).await;
    build_response(res.map(|(id, key)| {
        json!({
            "playerId": id,
            "key": key,
        })
    }))
}

// CHECKED
#[web::get("/player/{id}")]
async fn get_player(srv: GameState, id: Path<PlayerId>, req: HttpRequest) -> impl web::Responder {
    let Some(key) = get_player_key(&req) else {
        return build_response(Err(Errcode::NoPlayerKey));
    };
    let id = id.as_ref();

    let players = srv.players.read().await;
    let Some(player) = players.get(id) else {
        return build_response(Err(Errcode::PlayerNotFound(*id)));
    };
    let player = player.read().await;

    let res = if player.key == key {
        Ok(json!({
            "id": id,
            "name": player.name,
            "stations": player.stations,
            "money": player.money,
            "ships": serde_json::to_value(
                player.ships.values().collect::<Vec<&Ship>>()
            ).unwrap(),
            "costs": player.costs,
        }))
    } else {
        Ok(json!({
            "id": id,
            "name": player.name,
            "stations": player.stations,
        }))
    };
    build_response(res)
}

// CHECKED
#[web::get("/station/{station_id}")]
async fn get_station_status(
    srv: GameState,
    id: Path<StationId>,
    req: HttpRequest,
) -> impl web::Responder {
    let player = get_player!(srv, req);
    let station = get_station!(srv, player, id.as_ref());
    let station = station.read().await;

    build_response(Ok(json!({
        "id": station.id,
        "position": station.position,
        "crew": station.crew,
        "cargo": station.cargo,
        "idle_crew": station.idle_crew,
        "trader": station.trader,
    })))
}

// CHECKED
#[web::get("/station/{station_id}/shipyard/list")]
async fn list_shipyard_ships(
    srv: GameState,
    id: Path<StationId>,
    req: HttpRequest,
) -> impl web::Responder {
    let player = get_player!(srv, req);
    let station = get_station!(srv, player, id.as_ref());
    let station = station.read().await;

    let mut ships = vec![];
    for ship in station.shipyard.iter() {
        ships.push(json!({
            "id": ship.id,
            "modules": ship.modules,
            "reactor_power": ship.reactor_power,
            "cargo_capacity": ship.cargo.capacity,
            "fuel_tank_capacity": ship.fuel_tank_capacity,
            "hull_decay_capacity": ship.hull_decay_capacity,
            "price": ship.compute_price(),
        }));
    }
    build_response(Ok(json!({ "ships": ships })))
}

// CHECKED
#[web::get("/station/{station_id}/shipyard/buy/{id}")]
async fn shipyard_buy_ship(
    srv: GameState,
    args: Path<(StationId, ShipId)>,
    req: HttpRequest,
) -> impl web::Responder {
    let (station_id, ship_id) = args.as_ref();

    let player = get_player!(srv, req);
    let mut player = player.write().await;

    let station = get_station!(srv, station_id; player);
    let mut station = station.write().await;

    build_response(
        player
            .buy_ship(&mut station, *ship_id)
            .map(|v| json!({ "shipId": v, })),
    )
}

// CHECKED
// TODO IMPORTANT    Get ship ID here, and adapt prices based on the ranks of the modules
#[web::get("/station/{station_id}/shipyard/upgrade")]
async fn shipyard_list_upgrades(
    srv: GameState,
    station_id: Path<StationId>,
    req: HttpRequest,
) -> impl web::Responder {
    let player = get_player!(srv, req);
    let station = get_station!(srv, player, station_id.as_ref());
    let station = station.read().await;

    let mut res = BTreeMap::new();
    for upgr in ShipUpgrade::iter() {
        res.insert(
            upgr,
            json!({
                "price": station.get_ship_upgrade_price(&upgr),
                "description": upgr.description(),
            }),
        );
    }
    build_response(Ok(to_value(res).unwrap()))
}

// CHECKED
#[web::get("/station/{station_id}/shipyard/upgrade/{ship_id}/{upgrade_type}")]
async fn shipyard_buy_upgrade(
    srv: GameState,
    args: Path<(StationId, ShipId, String)>,
    req: HttpRequest,
) -> impl web::Responder {
    let (station_id, ship_id, upgrade_type) = args.as_ref();
    let Ok(upgrade_type) = ShipUpgrade::from_str(upgrade_type) else {
        return build_response(Err(Errcode::InvalidArgument("upgrade type")));
    };
    let player = get_player!(srv, req);
    let mut player = player.write().await;

    let station = get_station!(srv, station_id; player);
    let mut station = station.write().await;

    build_response(
        player
            .buy_ship_upgrade(&mut station, ship_id, &upgrade_type)
            .map(|v| json!({ "cost": v })),
    )
}

// CHECKED
#[web::get("/station/{station_id}/crew/hire/{crewtype}")]
async fn hire_crew(
    srv: GameState,
    args: Path<(StationId, String)>,
    req: HttpRequest,
) -> impl web::Responder {
    let (station_id, crewtype) = args.as_ref();
    let Ok(crewtype) = CrewMemberType::from_str(crewtype.as_str()) else {
        return build_response(Err(Errcode::InvalidArgument("crewtype")));
    };

    let player = get_player!(srv, req);
    let mut player = player.write().await;
    let galaxy = srv.galaxy.read().await;
    let station = get_station!(srv, station_id; player; galaxy);
    let mut station = station.write().await;

    let mut rng = rand::rng();
    let id = rng.random();
    let member = CrewMember::from(crewtype);
    station.idle_crew.0.insert(id, member);
    drop(station);
    player.update_wages(&galaxy).await;
    build_response(Ok(serde_json::json!({ "id": id })))
}

// CHECKED
#[web::get("/station/{station_id}/crew/upgrade/ship/{ship_id}")]
async fn get_crew_upgrades(
    srv: GameState,
    args: Path<(StationId, ShipId)>,
    req: HttpRequest,
) -> impl web::Responder {
    let (station_id, ship_id) = args.as_ref();

    let player = get_player!(srv, req);
    let player = player.read().await;

    let Some(ship) = player.ships.get(ship_id) else {
        return build_response(Err(Errcode::ShipNotFound(*ship_id)));
    };

    let station = get_station!(srv, station_id; player);
    let station = station.read().await;
    if ship.position != station.position {
        return build_response(Err(Errcode::ShipNotInStation));
    }

    let mut res = BTreeMap::new();
    for (cid, cm) in ship.crew.0.iter() {
        res.insert(
            cid,
            json!({
                "member-type": cm.member_type,
                "rank": cm.rank + 1,
                "price": cm.price_next_rank(),
            }),
        );
    }
    build_response(Ok(to_value(res).unwrap()))
}

// CHECKED
#[web::get("/station/{station_id}/crew/upgrade/ship/{ship_id}/{crew_id}")]
async fn buy_crew_upgrade(
    srv: GameState,
    args: Path<(StationId, ShipId, CrewId)>,
    req: HttpRequest,
) -> impl web::Responder {
    let (station_id, ship_id, crew_id) = args.as_ref();

    let player = get_player!(srv, req);
    let mut player = player.write().await;
    let galaxy = srv.galaxy.read().await;
    let station = get_station!(srv, station_id; player; galaxy);
    let station = station.read().await;

    let res = player.upgrade_crew_rank(&station, ship_id, crew_id);
    if res.is_ok() {
        drop(station);
        player.update_wages(&galaxy).await;
    }
    build_response(res.map(|(p, r)| json!({ "new-rank": r, "cost": p})))
}

// CHECKED
// TODO (#35)    Have an endpoint /station/{station_id}/crew/upgrade/{crew_id} instead
#[web::get("/station/{station_id}/crew/upgrade/trader")]
async fn upgrade_station_trader(
    station_id: Path<StationId>,
    srv: GameState,
    req: HttpRequest,
) -> impl web::Responder {
    let player = get_player!(srv, req);
    let mut player = player.write().await;
    let galaxy = srv.galaxy.read().await;
    let station = get_station!(srv, station_id.as_ref(); player; galaxy);
    let mut station = station.write().await;

    let res = player.upgrade_station_trader(station.deref_mut());
    if res.is_ok() {
        drop(station);
        player.update_wages(&galaxy).await;
    }
    build_response(res.map(|(p, r)| json!({ "new-rank": r, "cost": p })))
}

// CHECKED
#[web::get("/station/{station_id}/crew/assign/{crewid}/trading")]
async fn assign_trader(
    args: Path<(StationId, CrewId)>,
    srv: GameState,
    req: HttpRequest,
) -> impl web::Responder {
    let (station_id, crew_id) = args.as_ref();

    let player = get_player!(srv, req);
    let station = get_station!(srv, player, station_id);
    let mut station = station.write().await;

    build_response(station.assign_trader(*crew_id).map(|_| json!({})))
}

// CHECKED
#[web::get("/station/{station_id}/crew/assign/{crewid}/{shipid}/pilot")]
async fn assign_pilot(
    args: Path<(StationId, CrewId, ShipId)>,
    srv: GameState,
    req: HttpRequest,
) -> impl web::Responder {
    let (station_id, crew_id, ship_id) = args.as_ref();

    let player = get_player!(srv, req);
    let mut player = player.write().await;

    let station = get_station!(srv, station_id; player);
    let mut station = station.write().await;

    let Some(ship) = player.ships.get_mut(ship_id) else {
        return build_response(Err(Errcode::ShipNotFound(*ship_id)));
    };
    build_response(station.onboard_pilot(*crew_id, ship).map(|_| json!({})))
}

// CHECKED
#[web::get("/station/{station_id}/crew/assign/{crewid}/{shipid}/{modid}")]
async fn assign_operator(
    args: Path<(StationId, CrewId, ShipId, ShipModuleId)>,
    srv: GameState,
    req: HttpRequest,
) -> impl web::Responder {
    let (station_id, crew_id, ship_id, modid) = args.as_ref();

    let player = get_player!(srv, req);
    let mut player = player.write().await;

    let station = get_station!(srv, station_id; player);
    let mut station = station.write().await;

    let Some(ship) = player.ships.get_mut(ship_id) else {
        return build_response(Err(Errcode::ShipNotFound(*ship_id)));
    };
    build_response(
        station
            .onboard_operator(*crew_id, ship, modid)
            .map(|_| json!({})),
    )
}

// CHECKED
#[web::get("/station/{station_id}/scan")]
async fn scan(id: Path<StationId>, srv: GameState, req: HttpRequest) -> impl web::Responder {
    let player = get_player!(srv, req);
    let player = player.read().await;

    let galaxy = srv.galaxy.read().await;

    let station = get_station!(srv, id.as_ref(); player; galaxy);
    let station = station.read().await;

    let results = station.scan(&galaxy).await;
    build_response(Ok(to_value(&results).unwrap()))
}

// CHECKED
#[web::get("/station/{station_id}/shop/modules")]
async fn get_prices_ship_module(
    srv: GameState,
    id: Path<StationId>,
    req: HttpRequest,
) -> impl web::Responder {
    let player = get_player!(srv, req);
    let _station = get_station!(srv, player, id.as_ref()); // Ensure it exists

    // TODO (#22) Price based on station
    let mut res: BTreeMap<ShipModuleType, f64> = BTreeMap::new();
    for smod in ShipModuleType::iter() {
        let price = smod.get_price_buy();
        res.insert(smod, price);
    }

    build_response(Ok(to_value(res).unwrap()))
}

// CHECKED
#[web::get("/station/{station_id}/shop/modules/{ship_id}/buy/{modtype}")]
async fn buy_ship_module(
    srv: GameState,
    args: Path<(StationId, ShipId, String)>,
    req: HttpRequest,
) -> impl web::Responder {
    let (station_id, ship_id, modtype) = args.as_ref();
    let Ok(modtype) = ShipModuleType::from_str(modtype.as_str()) else {
        return build_response(Err(Errcode::InvalidArgument("modtype")));
    };

    let player = get_player!(srv, req);
    let mut player = player.write().await;

    build_response(
        player
            .buy_ship_module(station_id, ship_id, modtype)
            .map(|v| {
                json!({
                    "id": v,
                })
            }),
    )
}

// CHECKED
#[web::get("/station/{station_id}/shop/modules/{ship_id}/upgrade")]
async fn get_ship_module_upgrade_prices(
    srv: GameState,
    args: Path<(StationId, ShipId)>,
    req: HttpRequest,
) -> impl web::Responder {
    let (station_id, ship_id) = args.as_ref();

    let player = get_player!(srv, req);
    let player = player.read().await;

    let Some(ship) = player.ships.get(ship_id) else {
        return build_response(Err(Errcode::ShipNotFound(*ship_id)));
    };

    let station = get_station!(srv, station_id; player);
    let station = station.read().await;

    if ship.position != station.position {
        return build_response(Err(Errcode::ShipNotInStation));
    }

    let mut res = BTreeMap::new();
    for (id, smod) in ship.modules.iter() {
        res.insert(
            id,
            json!({
                "module-type": smod.modtype,
                "price": smod.price_next_rank(),
            }),
        );
    }
    build_response(Ok(to_value(res).unwrap()))
}

// CHECKED
#[web::get("/station/{station_id}/shop/modules/{ship_id}/upgrade/{modid}")]
async fn buy_ship_module_upgrade(
    srv: GameState,
    args: Path<(StationId, ShipId, ShipModuleId)>,
    req: HttpRequest,
) -> impl web::Responder {
    let (station_id, ship_id, mod_id) = args.as_ref();

    let player = get_player!(srv, req);
    let mut player = player.write().await;

    let station = get_station!(srv, station_id; player);
    let station = station.read().await;

    build_response(
        player
            .buy_ship_module_upgrade(&station, ship_id, mod_id)
            .map(|(c, r)| {
                json!({
                    "new-rank": r,
                    "cost": c,
                })
            }),
    )
}

// CHECKED
#[web::get("/station/{station_id}/shop/cargo/buy/{amount}")]
async fn buy_station_cargo(
    srv: GameState,
    args: Path<(StationId, usize)>,
    req: HttpRequest,
) -> impl web::Responder {
    let (id, amnt) = args.as_ref();

    let player = get_player!(srv, req);
    let mut player = player.write().await;

    let station = get_station!(srv, id; player);
    let mut station = station.write().await;

    build_response(
        station
            .buy_cargo(player.deref_mut(), amnt)
            .map(|v| to_value(v).unwrap()),
    )
}

// CHECKED
#[web::get("/station/{station_id}/upgrades")]
async fn get_station_upgrades(
    srv: GameState,
    id: Path<StationId>,
    req: HttpRequest,
) -> impl web::Responder {
    let player = get_player!(srv, req);
    let station = get_station!(srv, player, id.as_ref());
    let station = station.read().await;

    let cargoprice = station.cargo_price();
    let traderprice = station.trader.map(|trader| {
        let cm = station.crew.0.get(&trader).unwrap();
        cm.price_next_rank()
    });

    build_response(Ok(json!({
        "cargo-expansion": cargoprice,
        "trader-upgrade": traderprice,
    })))
}

// CHECKED
#[web::get("/station/{station_id}/refuel/{ship_id}")]
async fn refuel_ship(
    srv: GameState,
    args: Path<(StationId, ShipId)>,
    req: HttpRequest,
) -> impl web::Responder {
    let (station_id, ship_id) = args.as_ref();

    let player = get_player!(srv, req);
    let mut player = player.write().await;

    let station = get_station!(srv, station_id; player);
    let mut station = station.write().await;

    let Some(ship) = player.ships.get_mut(ship_id) else {
        return build_response(Err(Errcode::ShipNotFound(*ship_id)));
    };

    let res = station.refuel_ship(ship).map(|v| json!({"added-fuel": v}));
    build_response(res)
}

// CHECKED
#[web::get("/station/{station_id}/repair/{ship_id}")]
async fn repair_ship(
    srv: GameState,
    args: Path<(StationId, ShipId)>,
    req: HttpRequest,
) -> impl web::Responder {
    let (station_id, ship_id) = args.as_ref();
    let player = get_player!(srv, req);
    let mut player = player.write().await;

    let station = get_station!(srv, station_id; player);
    let mut station = station.write().await;

    let Some(ship) = player.ships.get_mut(ship_id) else {
        return build_response(Err(Errcode::ShipNotFound(*ship_id)));
    };

    let res = station.repair_ship(ship).map(|v| json!({"added-hull": v}));
    build_response(res)
}

// FIXME Sometimes under heavy load, sometimes get a "Ship not found"
// CHECKED
#[web::get("/ship/{ship_id}")]
async fn get_ship_status(
    srv: GameState,
    id: Path<ShipId>,
    req: HttpRequest,
) -> impl web::Responder {
    let player = get_player!(srv, req);
    let player = player.read().await;

    let Some(ship) = player.ships.get(id.as_ref()) else {
        return build_response(Err(Errcode::ShipNotFound(*id)));
    };
    build_response(Ok(to_value(ship).unwrap()))
}

// CHECKED
#[web::get("/ship/{ship_id}/travelcost/{x}/{y}/{z}")]
async fn compute_travel_costs(
    srv: GameState,
    args: Path<(ShipId, SpaceUnit, SpaceUnit, SpaceUnit)>,
    req: HttpRequest,
) -> impl web::Responder {
    let (id, x, y, z) = args.as_ref();

    let player = get_player!(srv, req);
    let player = player.read().await;

    let Some(ship) = player.ships.get(id) else {
        return build_response(Err(Errcode::ShipNotFound(*id)));
    };

    build_response(
        ship.compute_travel_costs((*x, *y, *z))
            .map(|v| to_value(v).unwrap()),
    )
}

// CHECKED
#[web::get("/ship/{ship_id}/navigate/{x}/{y}/{z}")]
async fn ask_navigate(
    srv: GameState,
    args: Path<(ShipId, SpaceUnit, SpaceUnit, SpaceUnit)>,
    req: HttpRequest,
) -> impl web::Responder {
    let (id, x, y, z) = args.as_ref();
    let coord = (*x, *y, *z);

    let player = get_player!(srv, req);
    let mut player = player.write().await;

    let Some(ship) = player.ships.get_mut(id) else {
        return build_response(Err(Errcode::ShipNotFound(*id)));
    };

    build_response(ship.set_travel(coord).map(|cost| json!(cost)))
}

// CHECKED
#[web::get("/ship/{ship_id}/navigation/stop")]
async fn stop_navigation(
    srv: GameState,
    args: Path<ShipId>,
    req: HttpRequest,
) -> impl web::Responder {
    let id = args.as_ref();

    let player = get_player!(srv, req);
    let mut player = player.write().await;

    let Some(ship) = player.ships.get_mut(id) else {
        return build_response(Err(Errcode::ShipNotFound(*id)));
    };
    build_response(ship.stop_navigation().map(|pos| json!({"position": pos})))
}

// CHECKED
#[web::get("/ship/{ship_id}/extraction/start")]
async fn start_extraction(
    srv: GameState,
    id: Path<ShipId>,
    req: HttpRequest,
) -> impl web::Responder {
    let player = get_player!(srv, req);
    let mut player = player.write().await;
    let Some(ship) = player.ships.get_mut(id.as_ref()) else {
        return build_response(Err(Errcode::ShipNotFound(*id)));
    };
    let galaxy = srv.galaxy.read().await;
    build_response(
        ship.start_extraction(&galaxy)
            .await
            .map(|v| to_value(v).unwrap()),
    )
}

// CHECKED
#[web::get("/ship/{ship_id}/extraction/stop")]
async fn stop_extraction(
    srv: GameState,
    id: Path<ShipId>,
    req: HttpRequest,
) -> impl web::Responder {
    let player = get_player!(srv, req);
    let mut player = player.write().await;

    let Some(ship) = player.ships.get_mut(id.as_ref()) else {
        return build_response(Err(Errcode::ShipNotFound(*id)));
    };

    build_response(ship.stop_extraction().map(|v| to_value(v).unwrap()))
}

// CHECKED
#[web::get("/ship/{ship_id}/unload/{resource}/{amount}")]
async fn unload_ship_cargo(
    srv: GameState,
    args: Path<(ShipId, String, f64)>,
    req: HttpRequest,
) -> impl web::Responder {
    let (id, resource, amnt) = args.as_ref();

    let Ok(resource) = Resource::from_str(resource) else {
        return build_response(Err(Errcode::InvalidArgument("resource")));
    };

    let player = get_player!(srv, req);
    let mut player = player.write().await;

    let Some(ship) = player.ships.get(id) else {
        return build_response(Err(Errcode::ShipNotFound(*id)));
    };

    let Some(station) = player.stations.iter().find(|(_, s)| *s == &ship.position) else {
        return build_response(Err(Errcode::ShipNotInStation));
    };

    let station = get_station!(srv, station.0; player);
    let mut station = station.write().await;

    let pid = player.id;
    let ship = player.ships.get_mut(id).unwrap();
    let res = ship.unload_cargo(&resource, *amnt, station.deref_mut());

    if let Ok(0.0) = res {
        srv.syslog
            .event(
                &pid,
                SyslogEvent::UnloadedNothing {
                    station_cargo: station.cargo.clone(),
                    ship_cargo: ship.cargo.clone(),
                },
            )
            .await;
    }
    build_response(res.map(|v| json!({ "unloaded": v })))
}

// CHECKED
#[web::get("/market/prices")]
async fn get_market_prices(srv: GameState) -> impl web::Responder {
    let market = srv.market.read().await;
    let res = to_value(market.deref()).unwrap();
    build_response(Ok(res))
}

// CHECKED
#[web::get("/market/{station_id}/buy/{resource}/{amnt}")]
async fn buy_resource(
    srv: GameState,
    args: Path<(StationId, String, f64)>,
    req: HttpRequest,
) -> impl web::Responder {
    let (station_id, resource, amnt) = args.as_ref();
    let Ok(resource) = Resource::from_str(resource) else {
        return build_response(Err(Errcode::InvalidArgument("resource")));
    };

    let player = get_player!(srv, req);
    let mut player = player.write().await;

    let station = get_station!(srv, station_id; player);
    let mut station = station.write().await;

    let mut market = srv.market.write().await;
    build_response(
        station
            .buy_resource(&resource, *amnt, player.deref_mut(), market.deref_mut())
            .map(|tx| to_value(tx).unwrap()),
    )
}

// CHECKED
#[web::get("/market/{station_id}/sell/{resource}/{amnt}")]
async fn sell_resource(
    srv: GameState,
    args: Path<(StationId, String, f64)>,
    req: HttpRequest,
) -> impl web::Responder {
    let (station_id, resource, amnt) = args.as_ref();
    let Ok(resource) = Resource::from_str(resource) else {
        return build_response(Err(Errcode::InvalidArgument("resource")));
    };

    let player = get_player!(srv, req);
    let mut player = player.write().await;

    let station = get_station!(srv, station_id; player);
    let mut station = station.write().await;

    let mut market = srv.market.write().await;
    let res = station
        .sell_resource(&resource, *amnt, player.deref_mut(), market.deref_mut())
        .map(|tx| to_value(tx).unwrap());
    build_response(res)
}

// CHECKED
#[web::get("/market/{station_id}/fee_rate")]
async fn get_fee_rate(
    srv: GameState,
    station_id: Path<StationId>,
    req: HttpRequest,
) -> impl web::Responder {
    let player = get_player!(srv, req);
    let station = get_station!(srv, player, station_id.as_ref());
    let station = station.read().await;

    let Some(trader) = station.trader else {
        return build_response(Err(Errcode::NoTraderAssigned));
    };

    let cm = station.crew.0.get(&trader).unwrap();
    let fee = fee_rate(cm.rank);

    build_response(Ok(json!({
        "fee_rate": fee,
    })))
}

// CHECKED
#[cfg(feature = "testing")]
#[web::get("/tick")]
async fn tick_server(srv: GameState) -> impl web::Responder {
    let Ok(_) = srv.send_sig.send(simeis_data::game::GameSignal::Tick).await else {
        return build_response(Err(Errcode::GameSignalSend));
    };
    build_response(Ok(json!({})))
}

#[cfg(feature = "testing")]
#[web::get("/tick/{n}")]
async fn tick_server_n(srv: GameState, n: Path<usize>) -> impl web::Responder {
    let n = n.as_ref().clone();
    for _ in 0..n {
        let Ok(_) = srv.send_sig.send(simeis_data::game::GameSignal::Tick).await else {
            return build_response(Err(Errcode::GameSignalSend));
        };
    }
    build_response(Ok(json!({})))
}

// CHECKED
#[web::get("/resources")]
async fn resources_info() -> impl web::Responder {
    let mut data = BTreeMap::new();
    for res in Resource::iter() {
        if res.mineable(u8::MAX) || res.suckable(u8::MAX) {
            data.insert(
                format!("{res:?}"),
                json!({
                    "base-price": res.base_price(),
                    "volume": res.volume(),
                    "difficulty": res.extraction_difficulty(),
                    "min-rank": res.min_rank(),
                }),
            );
        } else {
            data.insert(
                format!("{res:?}"),
                json!({
                    "base-price": res.base_price(),
                    "volume": res.volume(),
                    "solid": res.mineable(u8::MAX),
                }),
            );
        }
    }
    build_response(Ok(to_value(data).unwrap()))
}

// CHECKED
#[web::get("/gamestats")]
async fn gamestats(srv: GameState) -> impl web::Responder {
    let mut data = BTreeMap::new();
    let all_players = srv.players.read().await;
    let mut players = vec![];
    for (id, player) in all_players.iter() {
        players.push((id, player.read().await));
    }
    let galaxy = srv.galaxy.read().await;

    for (id, p) in players {
        let potential = {
            let mut s = 0.0;
            for (_, coord) in p.stations.iter() {
                let sta = galaxy.get_station(coord).await.unwrap();
                let station = sta.read().await;
                s += station
                    .cargo
                    .resources
                    .iter()
                    .map(|(r, amnt)| r.base_price() * amnt)
                    .sum::<f64>();
            }
            s
        };

        data.insert(
            id,
            json!({
                "name": p.name,
                "score": p.score,
                "potential": potential,
                "age": (Instant::now() - p.created).as_secs(),
                "lost": p.lost,
                "money": p.money,
                "stations": p.stations,
            }),
        );
    }
    build_response(Ok(to_value(data).unwrap()))
}

#[web::get("/version")]
async fn get_version() -> impl web::Responder {
    let v = env!("CARGO_PKG_VERSION");
    build_response(Ok(json!({"version": v})))
}

pub fn configure(srv: &mut ServiceConfig) {
    #[cfg(feature = "testing")]
    srv.service(tick_server).service(tick_server_n);

    srv.service(ping)
        .service(get_version)
        .service(gamestats)
        .service(resources_info)
        .service(get_syslogs)
        .service(hire_crew)
        .service(get_crew_upgrades)
        .service(buy_crew_upgrade)
        .service(upgrade_station_trader)
        .service(assign_pilot)
        .service(assign_operator)
        .service(assign_trader)
        .service(scan)
        .service(compute_travel_costs)
        .service(get_ship_status)
        .service(ask_navigate)
        .service(stop_navigation)
        .service(shipyard_buy_ship)
        .service(list_shipyard_ships)
        .service(shipyard_buy_upgrade)
        .service(shipyard_list_upgrades)
        .service(buy_ship_module)
        .service(get_ship_module_upgrade_prices)
        .service(buy_ship_module_upgrade)
        .service(get_prices_ship_module)
        .service(start_extraction)
        .service(stop_extraction)
        .service(unload_ship_cargo)
        .service(get_station_status)
        .service(get_station_upgrades)
        .service(buy_station_cargo)
        .service(refuel_ship)
        .service(repair_ship)
        .service(get_fee_rate)
        .service(get_market_prices)
        .service(buy_resource)
        .service(sell_resource)
        .service(get_player)
        .service(new_player);
}
