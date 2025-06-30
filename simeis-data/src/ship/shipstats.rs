use serde::{Deserialize, Serialize};

#[derive(Debug, Deserialize, Clone, Serialize, Default)]
pub struct ShipStats {
    pub speed: f64,
    pub fuel_consumption: f64,
    pub hull_usage_rate: f64,
}
