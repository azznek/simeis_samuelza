use serde::{Deserialize, Serialize};

use crate::crew::{Crew, CrewId, CrewMemberType};
use crate::errors::Errcode;
use crate::market::{Market, MarketTx};
use crate::player::Player;
use crate::ship::cargo::ShipCargo;
use crate::ship::module::ShipModuleId;
use crate::ship::resources::Resource;
use crate::ship::upgrade::ShipUpgrade;
use crate::ship::Ship;

use super::scan::ScanResult;
use super::{Galaxy, SpaceCoord};

const CARGO_BASE_PRICE: f64 = 2.0;
// For X units of cargo purshased, price goes from (base ^ n) to (base ^ (n+1))
const CARGO_PRICE_INCDIV: f64 = 1000.0;
const STATION_INIT_CARGO: f64 = 1000.0;

pub type StationId = u16;

// TODO (#43) Add refineries to create fuel & hull plate from raw resources
#[derive(Serialize, Deserialize, Debug)]
pub struct StationInfo {
    pub id: StationId,
    pub position: SpaceCoord,
}

impl StationInfo {
    // TODO (#27) Based on the scanner rank, get informations on crew and cargo
    pub fn scan(_rank: u8, station: &Station) -> StationInfo {
        StationInfo {
            id: station.id,
            position: station.position,
        }
    }
}

#[derive(Debug)]
pub struct Station {
    pub id: StationId,
    pub position: SpaceCoord,

    pub idle_crew: Crew,
    pub crew: Crew,
    pub shipyard: Vec<Ship>,
    pub cargo: ShipCargo,
    pub trader: Option<CrewId>,
}

impl Station {
    pub fn init(id: u16, position: super::SpaceCoord) -> Station {
        Station {
            id,
            position,
            idle_crew: Crew::default(),
            crew: Crew::default(),
            shipyard: Ship::init_shipyard(position),
            cargo: ShipCargo::with_capacity(STATION_INIT_CARGO),
            trader: None,
        }
    }

    // TODO (#27) Allow to build improvements for the scanner
    pub async fn scan(&self, galaxy: &Galaxy) -> ScanResult {
        galaxy.scan_sector(1, &self.position).await
    }

    pub fn cargo_price(&self) -> f64 {
        CARGO_BASE_PRICE.powf((self.cargo.capacity - STATION_INIT_CARGO) / CARGO_PRICE_INCDIV)
    }

    pub fn buy_cargo(&mut self, player: &mut Player, amnt: &usize) -> Result<&ShipCargo, Errcode> {
        let cost = (*amnt as f64) * self.cargo_price();
        if cost > player.money {
            return Err(Errcode::NotEnoughMoney(player.money, cost));
        }
        player.money -= cost;
        self.cargo.capacity += *amnt as f64;

        Ok(&self.cargo)
    }

    pub fn assign_trader(&mut self, id: CrewId) -> Result<(), Errcode> {
        let Some(cm) = self.idle_crew.0.remove(&id) else {
            return Err(Errcode::CrewMemberNotIdle(id));
        };

        self.crew.0.insert(id, cm);
        self.trader = Some(id);
        Ok(())
    }

    pub fn onboard_pilot(&mut self, id: CrewId, ship: &mut Ship) -> Result<(), Errcode> {
        let Some(cm) = self.idle_crew.0.get(&id) else {
            return Err(Errcode::CrewMemberNotIdle(id));
        };

        if cm.member_type != CrewMemberType::Pilot {
            return Err(Errcode::WrongCrewType(CrewMemberType::Pilot));
        }

        if ship.pilot.is_some() {
            return Err(Errcode::CrewNotNeeded);
        }
        ship.pilot = Some(id);
        ship.crew
            .0
            .insert(id, self.idle_crew.0.remove(&id).unwrap());
        ship.update_perf_stats();
        Ok(())
    }

    pub fn onboard_operator(
        &mut self,
        id: CrewId,
        ship: &mut Ship,
        modid: &ShipModuleId,
    ) -> Result<(), Errcode> {
        let Some(cm) = self.idle_crew.0.get(&id) else {
            return Err(Errcode::CrewMemberNotIdle(id));
        };

        if cm.member_type != CrewMemberType::Operator {
            return Err(Errcode::WrongCrewType(CrewMemberType::Pilot));
        }

        let Some(smod) = ship.modules.get_mut(modid) else {
            return Err(Errcode::NoSuchModule(*modid));
        };
        if !smod.need(&cm.member_type) {
            return Err(Errcode::CrewNotNeeded);
        }
        smod.operator = Some(id);
        ship.crew
            .0
            .insert(id, self.idle_crew.0.remove(&id).unwrap());
        Ok(())
    }

    pub fn buy_resource(
        &mut self,
        resource: &Resource,
        amnt: f64,
        player: &mut Player,
        market: &mut Market,
    ) -> Result<MarketTx, Errcode> {
        let Some(trader) = self.trader else {
            return Err(Errcode::NoTraderAssigned);
        };
        let cm = self.crew.0.get(&trader).unwrap();
        let can_cargo = self.cargo.space_for(resource);
        let amnt = amnt.min(can_cargo);
        if amnt == 0.0 {
            return Err(Errcode::BuyNothing);
        }

        let tx = market.buy(cm, resource, amnt);
        player.money -= tx.removed_money.unwrap();
        player.score -= tx.removed_money.unwrap();
        let (r, a) = tx.added_cargo.unwrap();
        self.cargo.add_resource(&r, a);
        Ok(tx)
    }

    pub fn sell_resource(
        &mut self,
        resource: &Resource,
        amnt: f64,
        player: &mut Player,
        market: &mut Market,
    ) -> Result<MarketTx, Errcode> {
        let Some(trader) = self.trader else {
            return Err(Errcode::NoTraderAssigned);
        };
        let cm = self.crew.0.get(&trader).unwrap();
        let Some(can_cargo) = self.cargo.resources.get(resource) else {
            return Err(Errcode::SellNothing);
        };
        let amnt = amnt.min(*can_cargo);
        if amnt <= 0.0 {
            return Err(Errcode::SellNothing);
        }

        let tx = market.sell(cm, resource, amnt);
        player.money += tx.added_money.unwrap();
        player.score += tx.added_money.unwrap();
        let (r, a) = tx.removed_cargo.unwrap();
        let unloaded = self.cargo.unload(&r, a);
        debug_assert_eq!(unloaded, a);
        Ok(tx)
    }

    pub fn refuel_ship(&mut self, ship: &mut Ship) -> Result<f64, Errcode> {
        if self.position != ship.position {
            return Err(Errcode::ShipNotInStation);
        }
        let Some(qty) = self.cargo.resources.get(&Resource::Fuel) else {
            return Err(Errcode::NoFuelInCargo);
        };
        if *qty == 0.0 {
            return Err(Errcode::NoFuelInCargo);
        }
        debug_assert!(ship.fuel_tank >= 0.0);
        debug_assert!(ship.fuel_tank_capacity >= ship.fuel_tank);
        let needed = ship.fuel_tank_capacity - ship.fuel_tank;
        let unloaded = self.cargo.unload(&Resource::Fuel, needed.min(*qty));
        ship.fuel_tank += unloaded;
        debug_assert!(ship.fuel_tank_capacity >= ship.fuel_tank);
        Ok(unloaded)
    }

    pub fn repair_ship(&mut self, ship: &mut Ship) -> Result<f64, Errcode> {
        if self.position != ship.position {
            return Err(Errcode::ShipNotInStation);
        }
        let Some(qty) = self.cargo.resources.get(&Resource::HullPlate) else {
            return Err(Errcode::NoHullPlateInCargo);
        };
        if *qty == 0.0 {
            return Err(Errcode::NoHullPlateInCargo);
        }
        debug_assert!(ship.hull_decay_capacity >= ship.hull_decay);

        let amnt = ship.hull_decay.min(*qty);
        if amnt == 0.0 {
            return Ok(0.0);
        }
        let unloaded = self.cargo.unload(&Resource::HullPlate, amnt);
        ship.hull_decay -= unloaded;
        debug_assert!(
            ship.hull_decay_capacity >= ship.hull_decay,
            "{} < {}",
            ship.hull_decay_capacity,
            ship.hull_decay
        );
        debug_assert!(ship.hull_decay >= 0.0, "{}", ship.hull_decay);
        debug_assert!(unloaded >= 0.0, "{}", unloaded);
        Ok(unloaded)
    }

    pub fn get_ship_upgrade_price(&self, upgrade: &ShipUpgrade) -> f64 {
        // TODO (#22) Modify price based on station economy metrics
        upgrade.get_price()
    }
}

// TODO (#22)    Have a "ship price rate" metric for a station, that afffects the ship prices
//     Correlated to the price of the resources on the station
