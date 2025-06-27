use serde::{Deserialize, Serialize};
use strum::{EnumIter, EnumString, IntoStaticStr};

use super::{Ship, CARGO_CAP_PRICE, HULL_DECAY_CAP_PRICE, REACTOR_POWER_PRICE, SHIELD_PRICE};

const CARGO_EXP_ADD_CAP: f64 = 100.0;
const REACTOR_UPG_ADD: u16 = 1;
const HULL_UPG_ADD: f64 = 100.0;
const SHIELD_UPG_ADD: u16 = 1;

const REACTOR_OPT_DEC_FUELCONS: f64 = 5.0 / 100.0;
const REACTOR_OPT_PRICE: f64 = 1000.0;

#[derive(
    EnumIter,
    EnumString,
    IntoStaticStr,
    Debug,
    Serialize,
    Deserialize,
    Ord,
    PartialOrd,
    PartialEq,
    Eq,
    Clone,
    Copy,
)]
#[strum(ascii_case_insensitive)]
pub enum ShipUpgrade {
    CargoExpansion,
    ReactorUpgrade,
    HullUpgrade,
    Shield,
}

impl ShipUpgrade {
    pub fn get_price(&self) -> f64 {
        match self {
            ShipUpgrade::CargoExpansion => CARGO_EXP_ADD_CAP * CARGO_CAP_PRICE,
            ShipUpgrade::ReactorUpgrade => (REACTOR_UPG_ADD as f64) * REACTOR_POWER_PRICE,
            ShipUpgrade::HullUpgrade => HULL_UPG_ADD * HULL_DECAY_CAP_PRICE,
            ShipUpgrade::Shield => (SHIELD_UPG_ADD as f64) * SHIELD_PRICE,
        }
    }

    pub fn install(&self, ship: &mut Ship) {
        match self {
            ShipUpgrade::CargoExpansion => ship.cargo.capacity += CARGO_EXP_ADD_CAP,
            ShipUpgrade::ReactorUpgrade => ship.reactor_power += REACTOR_UPG_ADD,
            ShipUpgrade::HullUpgrade => ship.hull_decay_capacity += HULL_UPG_ADD,
            ShipUpgrade::Shield => ship.shield_power += SHIELD_UPG_ADD,
        }
        ship.update_perf_stats();
    }

    pub fn description(&self) -> String {
        match self {
            ShipUpgrade::CargoExpansion => format!("Adds {CARGO_EXP_ADD_CAP} of cargo capacity"),
            ShipUpgrade::ReactorUpgrade => format!(
                "Increase the reactor power by {REACTOR_UPG_ADD}, improves the ship's speed"
            ),
            ShipUpgrade::HullUpgrade => {
                format!("Increase the hull decay capacity by {HULL_UPG_ADD}")
            }
            ShipUpgrade::Shield => "Reduce the damage and usure of the hull".to_string(),
        }
    }
}
