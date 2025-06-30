use serde::{Deserialize, Serialize};

use crate::{
    errors::Errcode,
    galaxy::{get_delta, get_direction, get_distance, SpaceCoord},
};

use super::Ship;

#[derive(Serialize, Deserialize)]
pub struct Travel {
    pub destination: SpaceCoord,
}
impl Travel {
    pub fn new(destination: SpaceCoord) -> Travel {
        Travel { destination }
    }

    pub fn compute_costs(&self, ship: &Ship) -> Result<TravelCost, Errcode> {
        if ship.pilot.is_none() {
            return Err(Errcode::NoPilotAssigned);
        }
        let distance = get_distance(&ship.position, &self.destination);
        if distance == 0.0 {
            return Err(Errcode::NullDistance);
        }

        let direction = get_direction(&ship.position, &self.destination);
        let time_secs = distance / ship.stats.speed;
        let fuel_consumption = ship.stats.fuel_consumption * time_secs;
        let hull_usage = ship.stats.hull_usage_rate * distance;

        Ok(TravelCost {
            direction,
            distance,
            duration: time_secs,
            fuel_consumption,
            hull_usage,
        })
    }
}

#[derive(Serialize, Deserialize, Debug)]
pub struct TravelCost {
    pub direction: (f64, f64, f64),
    pub distance: f64,
    pub duration: f64,
    pub fuel_consumption: f64,
    pub hull_usage: f64,
}

impl TravelCost {
    pub fn have_enough(&self, ship: &Ship) -> bool {
        (ship.fuel_tank >= self.fuel_consumption)
            && (ship.hull_decay_capacity - ship.hull_decay) >= self.hull_usage
    }
}

#[derive(Deserialize, Clone, Serialize, Debug)]
pub struct FlightData {
    pub start: SpaceCoord,
    pub destination: SpaceCoord,
    pub delta: (f64, f64, f64),

    pub direction: (f64, f64, f64),
    pub dist_done: f64,
    pub dist_tot: f64,
}

impl FlightData {
    pub fn new(start: SpaceCoord, cost: &TravelCost, travel: &Travel) -> FlightData {
        FlightData {
            dist_done: 0.0,
            dist_tot: cost.distance,
            direction: cost.direction,
            delta: get_delta(&start, &travel.destination),
            destination: travel.destination,
            start,
        }
    }
}

#[test]
fn test_compute_cost_addition() {
    const EPS: f64 = 1e-7;
    for n in 1..=1000 {
        let mut ship = Ship::random((0, 0, 0));
        ship.crew.0.insert(
            0,
            crate::crew::CrewMember {
                member_type: crate::crew::CrewMemberType::Pilot,
                rank: 1,
            },
        );
        ship.pilot = Some(0);
        ship.update_perf_stats();
        let c1 = ship.compute_travel_costs((n, n, n)).unwrap();
        println!("{n} {c1:?}");
        assert!(!c1.duration.is_infinite());
        assert!(!c1.fuel_consumption.is_nan());
        // assert_eq!(c1.direction, (1.0, 0.0, 0.0));
        for x in 1..=4 {
            let c2 = ship.compute_travel_costs((n * x, n * x, n * x)).unwrap();
            println!("{n}x{x} {c2:?}");
            assert!(
                c2.distance - ((x as f64) * c1.distance) < EPS,
                "Wrong {x}x distance"
            );
            assert!(
                c2.duration - ((x as f64) * c1.duration) < EPS,
                "Wrong {x}x duration"
            );
            assert!(
                c2.fuel_consumption - ((x as f64) * c1.fuel_consumption) < EPS,
                "Wrong {x}x consumption"
            );
            assert!(
                c2.hull_usage - ((x as f64) * c1.hull_usage) < EPS,
                "Wrong {x}x hull usage"
            );
        }
        println!();
    }

    let mut ship = Ship::random((0, 0, 0));
    ship.crew.0.insert(
        0,
        crate::crew::CrewMember {
            member_type: crate::crew::CrewMemberType::Pilot,
            rank: 1,
        },
    );
    ship.pilot = Some(0);
    ship.update_perf_stats();

    let c1 = ship.compute_travel_costs((5, 5, 5)).unwrap();
    let c3 = ship.compute_travel_costs((10, 10, 10)).unwrap();

    ship.position = (5, 5, 5);
    let c2 = ship.compute_travel_costs((10, 10, 10)).unwrap();

    assert_eq!(c1.distance + c2.distance, c3.distance);
    assert_eq!(c1.duration + c2.duration, c3.duration);
    assert_eq!(
        c1.fuel_consumption + c2.fuel_consumption,
        c3.fuel_consumption
    );
    assert_eq!(c1.hull_usage + c2.hull_usage, c3.hull_usage);
    assert_eq!(c1.direction, c2.direction);
    assert_eq!(c1.direction, c3.direction);
}
