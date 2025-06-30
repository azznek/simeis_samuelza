use serde::{Deserialize, Serialize};
use std::collections::BTreeMap;
use strum::{EnumString, IntoStaticStr};

const WAGE_INC_RANK_POWF: f64 = 0.85;
const RANK_PRICE_WAGE_MULT: f64 = 1900.0;

pub type CrewId = u32;

#[derive(Debug, Clone, Deserialize, Default, Serialize)]
pub struct Crew(pub BTreeMap<CrewId, CrewMember>);
impl Crew {
    pub fn sum_wages(&self) -> f64 {
        self.0.values().map(|crew| crew.wage()).sum::<f64>()
    }
}

#[derive(Debug, Clone, Deserialize, Serialize)]
pub struct CrewMember {
    pub member_type: CrewMemberType,
    pub rank: u8,
}

impl From<CrewMemberType> for CrewMember {
    fn from(member_type: CrewMemberType) -> Self {
        CrewMember {
            member_type,
            rank: 1,
        }
    }
}

impl CrewMember {
    pub fn wage(&self) -> f64 {
        let base = match self.member_type {
            CrewMemberType::Pilot => 5.5,
            CrewMemberType::Operator => 0.9,
            CrewMemberType::Trader => 2.6,
            CrewMemberType::Soldier => 1.5,
        };
        base * (self.rank as f64).powf(WAGE_INC_RANK_POWF)
    }

    #[inline]
    pub fn price_next_rank(&self) -> f64 {
        self.wage() * RANK_PRICE_WAGE_MULT
    }
}

#[allow(dead_code)]
#[derive(EnumString, IntoStaticStr, Debug, Serialize, Deserialize, Clone, PartialEq, Eq)]
#[strum(ascii_case_insensitive)]
pub enum CrewMemberType {
    Pilot,
    Operator,
    Trader,
    Soldier,
}
