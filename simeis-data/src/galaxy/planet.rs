use serde::{Deserialize, Serialize};

use crate::ship::resources::Resource;

use super::SpaceCoord;

// Informations that can be scanned from a planet
#[derive(Clone, Serialize, Deserialize, Debug)]
pub struct PlanetInfo {
    pub position: SpaceCoord,
    pub temperature: u16,
    pub solid: bool,
}

impl PlanetInfo {
    pub fn scan(_rank: u8, planet: &Planet) -> PlanetInfo {
        PlanetInfo {
            position: planet.position,
            temperature: planet.temperature,
            solid: planet.solid,
        }
    }
}

#[derive(Debug)]
pub struct Planet {
    pub position: SpaceCoord,
    temperature: u16,
    solid: bool,
}

impl Planet {
    pub fn random<R: rand::Rng>(coord: SpaceCoord, rng: &mut R) -> Planet {
        Planet {
            solid: rng.random_bool(0.4),
            temperature: rng.random(),
            position: coord,
        }
    }

    // TODO (#34) Make this depend on the conditions, temperature, etc...
    #[allow(clippy::if_same_then_else)]
    pub fn resource_density(&self, resource: &Resource) -> f64 {
        if self.solid && resource.mineable(u8::MAX) {
            6.25
        } else if !self.solid && resource.suckable(u8::MAX) {
            6.25
        } else {
            0.0
        }
    }
}
