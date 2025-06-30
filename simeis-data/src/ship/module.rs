use serde::{Deserialize, Serialize};
use strum::{EnumIter, EnumString, IntoEnumIterator, IntoStaticStr};

use super::resources::Resource;
use crate::crew::{Crew, CrewId, CrewMemberType};
use crate::galaxy::planet::Planet;

const MOD_UPG_POWF_DIV: f64 = 75.0;
const EXTRACTION_RATE_RANK_POWF: f64 = 0.45;
const EXRATE_DIFF_FACT: f64 = 2.5;
const EXRATE_FACT: f64 = 0.6;

pub type ShipModuleId = u16;

#[derive(
    EnumIter,
    EnumString,
    IntoStaticStr,
    Debug,
    Clone,
    Serialize,
    Deserialize,
    PartialEq,
    Eq,
    PartialOrd,
    Ord,
)]
#[strum(ascii_case_insensitive)]
pub enum ShipModuleType {
    Miner,
    GasSucker,
}

impl ShipModuleType {
    pub fn new_module(self) -> ShipModule {
        ShipModule {
            operator: None,
            modtype: self,
            totalcost: 0.0,
            rank: 1,
        }
    }

    #[inline]
    pub fn get_price_buy(&self) -> f64 {
        match self {
            ShipModuleType::Miner | ShipModuleType::GasSucker => 4500.0,
        }
    }
}

#[derive(Debug, Deserialize, Serialize, Clone)]
pub struct ShipModule {
    pub operator: Option<CrewId>,
    pub modtype: ShipModuleType,
    pub rank: u8,
    pub totalcost: f64,
}

impl ShipModule {
    #[inline]
    pub fn price_next_rank(&self) -> f64 {
        let num = MOD_UPG_POWF_DIV - 1.0 + (self.rank as f64);
        self.modtype.get_price_buy().powf(num / MOD_UPG_POWF_DIV)
    }

    // Returns
    pub fn need(&self, ctype: &CrewMemberType) -> bool {
        match self.modtype {
            ShipModuleType::Miner | ShipModuleType::GasSucker => {
                ctype == &CrewMemberType::Operator && self.operator.is_none()
            }
        }
    }

    pub fn can_extract(&self, crew: &Crew, planet: &Planet) -> Vec<(Resource, f64)> {
        let Some(ref opid) = self.operator else {
            log::debug!("No operator");
            return vec![];
        };

        let cm = crew.0.get(opid).unwrap();
        let all_resources = Resource::iter()
            .map(|r| (r, planet.resource_density(&r)))
            .filter(|(_, d)| *d > 0.0);

        match self.modtype {
            ShipModuleType::Miner => all_resources
                .filter(|(r, _)| r.mineable(cm.rank))
                .map(|(r, density)| (r, self.extraction_rate(&r, cm.rank, density)))
                .collect(),
            ShipModuleType::GasSucker => all_resources
                .filter(|(r, _)| r.suckable(cm.rank))
                .map(|(r, density)| (r, self.extraction_rate(&r, cm.rank, density)))
                .collect(),
        }
    }

    pub fn extraction_rate(&self, resource: &Resource, oprank: u8, density: f64) -> f64 {
        let rank = ((oprank - resource.min_rank()) as f64) * (self.rank as f64);
        let difficulty = resource.extraction_difficulty().powf(EXRATE_DIFF_FACT);
        density * (rank / difficulty).powf(EXRATE_FACT)
    }
}
