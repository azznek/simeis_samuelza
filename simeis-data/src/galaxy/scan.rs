use std::ops::Deref;

use serde::{Deserialize, Serialize};

use super::planet::PlanetInfo;
use super::station::StationInfo;
use super::{get_distance, SpaceCoord, SpaceObject};

#[derive(Serialize, Deserialize, Debug)]
pub struct ScanResult {
    pub planets: Vec<PlanetInfo>,
    pub stations: Vec<StationInfo>,
}

impl ScanResult {
    pub fn empty() -> ScanResult {
        ScanResult {
            planets: vec![],
            stations: vec![],
        }
    }

    pub async fn add(&mut self, rank: u8, obj: &SpaceObject) {
        match obj {
            SpaceObject::BaseStation(station) => {
                let station = station.read().await; // OK
                self.stations.push(StationInfo::scan(rank, station.deref()));
            }
            SpaceObject::Planet(planet) => {
                self.planets.push(PlanetInfo::scan(rank, planet.as_ref()))
            }
        }
    }

    pub fn get_closest_planet(&self, pos: &SpaceCoord) -> Option<PlanetInfo> {
        let mut planets = self.planets.clone();
        planets.sort_by(|a, b| {
            let dist_a = get_distance(pos, &a.position);
            let dist_b = get_distance(pos, &b.position);
            dist_a.total_cmp(&dist_b)
        });
        planets.into_iter().next()
    }
}
