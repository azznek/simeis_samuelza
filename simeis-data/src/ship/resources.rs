use std::collections::BTreeMap;

use serde::{Deserialize, Serialize};
use strum::{EnumIter, EnumString, IntoStaticStr};

use crate::galaxy::planet::Planet;

use super::{cargo::ShipCargo, Ship};

#[derive(
    EnumIter,
    EnumString,
    IntoStaticStr,
    Debug,
    Serialize,
    Deserialize,
    PartialEq,
    Eq,
    PartialOrd,
    Ord,
    Clone,
    Copy,
)]
#[strum(ascii_case_insensitive)]
pub enum Resource {
    // Solid or liquid
    Stone,
    Iron,
    Copper,
    Gold,

    // Gaseous
    Helium,
    Ozone,
    Freon,
    Oxygen,

    // Crafted
    Fuel,
    HullPlate,
}

impl Resource {
    pub fn scored(&self) -> bool {
        matches!(self, Resource::Fuel | Resource::HullPlate)
    }

    // TODO (#24) Get from configuration
    #[inline]
    pub const fn base_price(&self) -> f64 {
        match self {
            Resource::Stone | Resource::Helium => 4.0 * 2.0,
            Resource::Iron | Resource::Ozone => 16.0 * 2.0,
            Resource::Copper | Resource::Freon => 46.0 * 2.0,
            Resource::Gold | Resource::Oxygen => 80.0 * 2.0,
            Resource::Fuel => 1.9,
            Resource::HullPlate => 0.75,
        }
    }

    pub fn volume(&self) -> f64 {
        match self {
            Resource::Stone | Resource::Helium => 0.75,
            Resource::Iron | Resource::Ozone => 2.5,
            Resource::Copper | Resource::Freon => 3.0,
            Resource::Gold | Resource::Oxygen => 0.25,
            Resource::Fuel => 2.0,
            Resource::HullPlate => 0.05,
        }
    }

    pub fn extraction_difficulty(&self) -> f64 {
        match self {
            Resource::Stone | Resource::Helium => 0.25,
            Resource::Iron | Resource::Ozone => 0.7,
            Resource::Copper | Resource::Freon => 1.9,
            Resource::Gold | Resource::Oxygen => 2.95,

            // All the things that are only crafted
            _ => unreachable!("Extraction difficulty on crafted resources"),
        }
    }

    pub fn min_rank(&self) -> u8 {
        match self {
            Resource::Stone | Resource::Helium => 0,
            Resource::Iron | Resource::Ozone => 2,
            Resource::Copper | Resource::Freon => 5,
            Resource::Gold | Resource::Oxygen => 9,
            Resource::Fuel | Resource::HullPlate => 0,
        }
    }

    pub fn mineable(&self, rank: u8) -> bool {
        match self {
            Resource::Stone | Resource::Iron | Resource::Copper | Resource::Gold => {
                rank > self.min_rank()
            }
            _ => false,
        }
    }

    pub fn suckable(&self, rank: u8) -> bool {
        match self {
            Resource::Helium | Resource::Ozone | Resource::Freon | Resource::Oxygen => {
                rank > self.min_rank()
            }
            _ => false,
        }
    }
}

#[derive(Clone, Serialize, Deserialize, Debug)]
pub struct ExtractionInfo(pub BTreeMap<Resource, f64>);
impl ExtractionInfo {
    pub fn create(ship: &Ship, planet: &Planet) -> Self {
        let mut extraction = BTreeMap::new();
        for (_, smod) in ship.modules.iter() {
            for (res, rate) in smod.can_extract(&ship.crew, planet) {
                if let Some(rrate) = extraction.get_mut(&res) {
                    *rrate += rate;
                } else {
                    extraction.insert(res, rate);
                }
            }
        }
        ExtractionInfo(extraction)
    }

    pub fn update_cargo(&self, cargo: &mut ShipCargo, tdelta: f64) -> bool {
        for (res, rate) in self.0.iter() {
            cargo.add_resource(res, *rate * tdelta);
        }
        cargo.is_full()
    }

    pub fn time_before_cargo_full(&self, cargocap: f64) -> std::time::Duration {
        let mut vol_per_sec = 0.0;
        for (res, rate) in self.0.iter() {
            vol_per_sec += res.volume() * rate;
        }
        std::time::Duration::from_secs_f64(cargocap / vol_per_sec)
    }
}
