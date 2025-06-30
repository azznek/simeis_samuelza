use rand::RngCore;
use std::collections::hash_map::DefaultHasher;
use std::collections::BTreeMap;
use std::hash::Hasher;
use std::time::Instant;

use crate::crew::CrewId;
use crate::errors::Errcode;
use crate::galaxy::station::{Station, StationId};
use crate::galaxy::{Galaxy, SpaceCoord};
use crate::ship::module::{ShipModuleId, ShipModuleType};
use crate::ship::upgrade::ShipUpgrade;
use crate::ship::{Ship, ShipId};
use crate::syslog::{SyslogEvent, SyslogRecv};

const INIT_MONEY: f64 = 72000.0;

pub type PlayerId = u16;
pub type PlayerKey = [u8; 128];

// Game state for a single player
pub struct Player {
    pub created: Instant,
    pub id: PlayerId,
    pub key: PlayerKey,
    pub score: f64,
    pub lost: bool,

    pub name: String,
    pub money: f64,
    pub costs: f64,

    pub stations: BTreeMap<StationId, SpaceCoord>,
    pub ships: BTreeMap<ShipId, Ship>,
}

impl Player {
    pub fn new(station: (StationId, SpaceCoord), name: String) -> Player {
        let mut hasher = DefaultHasher::new();
        hasher.write(name.as_bytes());
        let mut rng = rand::rng();
        let mut randbytes = [0; 128];
        rng.fill_bytes(&mut randbytes);

        #[allow(unused_mut)]
        let mut money = INIT_MONEY;

        #[cfg(feature = "testing")]
        if name.starts_with("test-rich") {
            money *= 10000.0;
        }
        let mut stations = BTreeMap::new();
        stations.insert(station.0, station.1);
        Player {
            created: Instant::now(),
            key: randbytes,
            id: (hasher.finish() % (PlayerId::MAX as u64)) as PlayerId,
            lost: false,

            money,
            score: 0.0,
            costs: 0.0,

            name,
            stations,
            ships: BTreeMap::new(),
        }
    }

    // SAFETY Will deadlock if a &mut station exists when this is called
    pub async fn update_wages(&mut self, galaxy: &Galaxy) {
        self.costs = 0.0;
        let mut stations = vec![];
        for coord in self.stations.values() {
            stations.push(galaxy.get_station(coord).await.unwrap());
        }

        for station in stations {
            // Deadlock because of this
            let station = station.read().await;
            self.costs += station.crew.sum_wages();
            self.costs += station.idle_crew.sum_wages();
        }
        self.costs += self
            .ships
            .values()
            .map(|ship| ship.crew.sum_wages())
            .sum::<f64>();
    }

    pub async fn update_money(&mut self, syslog: &SyslogRecv, tdelta: f64) {
        let before = self.money < (self.costs * 60.0);
        self.money -= self.costs * tdelta;
        let after = self.money < (self.costs * 60.0);
        if after && !before {
            let tleft = std::time::Duration::from_secs_f64(self.money / self.costs);
            syslog.event(self.id, SyslogEvent::LowFunds(tleft)).await;
        }
        if self.money < 0.0 && !self.lost {
            self.lost = true;
            syslog.event(self.id, SyslogEvent::GameLost).await;
            // TODO (#19)  Allow to create a new game with the same name if old one lost
            // TODO (#19)  What to do with its resources, ships, etc...
        }
    }

    pub fn buy_ship(&mut self, station: &mut Station, id: ShipId) -> Result<ShipId, Errcode> {
        let ship_opt = {
            let mut data = None;
            for (n, ship) in station.shipyard.iter().enumerate() {
                if ship.id == id {
                    data = Some((n, ship.compute_price()));
                }
            }
            data
        };

        let Some((index, price)) = ship_opt else {
            return Err(Errcode::ShipNotFound(id));
        };

        if price > self.money {
            return Err(Errcode::NotEnoughMoney(self.money, price));
        }

        let mut ship = station.shipyard.remove(index);
        let ship_id = ship.id;
        ship.update_perf_stats();
        ship.fuel_tank = ship.fuel_tank_capacity;
        self.money -= price;
        self.ships.insert(id, ship);

        let pos = station.position;
        station.shipyard.push(Ship::random(pos));
        Ok(ship_id)
    }

    pub fn buy_ship_module(
        &mut self,
        station_id: &StationId,
        ship_id: &ShipId,
        modtype: ShipModuleType,
    ) -> Result<ShipModuleId, Errcode> {
        let Some(station) = self.stations.get(station_id) else {
            return Err(Errcode::NoSuchStation(*station_id));
        };

        let Some(ship) = self.ships.get_mut(ship_id) else {
            return Err(Errcode::ShipNotFound(*ship_id));
        };

        if station != &ship.position {
            return Err(Errcode::ShipNotInStation);
        }

        let price = modtype.get_price_buy();
        if self.money < price {
            return Err(Errcode::NotEnoughMoney(self.money, price));
        }
        self.money -= price;
        let id = (ship.modules.len() + 1) as ShipModuleId;
        ship.modules.insert(id, modtype.new_module());
        Ok(id)
    }

    pub fn buy_ship_upgrade(
        &mut self,
        station: &mut Station,
        ship_id: &ShipId,
        upgrade: &ShipUpgrade,
    ) -> Result<f64, Errcode> {
        let Some(ship) = self.ships.get_mut(ship_id) else {
            return Err(Errcode::ShipNotFound(*ship_id));
        };

        let price = station.get_ship_upgrade_price(upgrade);
        if price > self.money {
            return Err(Errcode::NotEnoughMoney(self.money, price));
        }

        self.money -= price;
        upgrade.install(ship);
        Ok(price)
    }

    pub fn buy_ship_module_upgrade(
        &mut self,
        station: &Station,
        ship_id: &ShipId,
        mod_id: &ShipModuleId,
    ) -> Result<(f64, u8), Errcode> {
        let Some(ship) = self.ships.get_mut(ship_id) else {
            return Err(Errcode::ShipNotFound(*ship_id));
        };
        if ship.position != station.position {
            return Err(Errcode::ShipNotInStation);
        }
        let Some(ref mut module) = ship.modules.get_mut(mod_id) else {
            return Err(Errcode::NoSuchModule(*mod_id));
        };
        let price = module.price_next_rank();
        if price > self.money {
            return Err(Errcode::NotEnoughMoney(self.money, price));
        }

        self.money -= price;
        module.rank += 1;

        Ok((price, module.rank))
    }

    pub fn upgrade_crew_rank(
        &mut self,
        station: &Station,
        ship_id: &ShipId,
        crew_id: &CrewId,
    ) -> Result<(f64, u8), Errcode> {
        let Some(ship) = self.ships.get_mut(ship_id) else {
            return Err(Errcode::ShipNotFound(*ship_id));
        };
        if ship.position != station.position {
            return Err(Errcode::ShipNotInStation);
        }
        let res = {
            let Some(ref mut cm) = ship.crew.0.get_mut(crew_id) else {
                return Err(Errcode::CrewMemberNotFound(*crew_id));
            };

            let price = cm.price_next_rank();
            if price > self.money {
                return Err(Errcode::NotEnoughMoney(self.money, price));
            }

            self.money -= price;
            cm.rank += 1;
            (price, cm.rank)
        };
        ship.update_perf_stats();
        Ok(res)
    }

    pub fn upgrade_station_trader(&mut self, station: &mut Station) -> Result<(f64, u8), Errcode> {
        let Some(trader_id) = station.trader else {
            return Err(Errcode::NoTraderAssigned);
        };
        let cm = station.crew.0.get_mut(&trader_id).unwrap();
        let price = cm.price_next_rank();
        if price > self.money {
            return Err(Errcode::NotEnoughMoney(self.money, price));
        }
        self.money -= price;
        cm.rank += 1;
        Ok((price, cm.rank))
    }
}
