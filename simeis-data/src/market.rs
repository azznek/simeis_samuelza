use rand::Rng;
use rand_distr::{Distribution, Normal};
use serde::{Deserialize, Serialize};
use std::collections::BTreeMap;
use strum::IntoEnumIterator;

use crate::{crew::CrewMember, ship::resources::Resource};

const MAX_AVG_AMPL: f64 = 5.0 / 100.0;
const STD_DIV: f64 = 1.5;
pub const MARKET_CHANGE_SEC: f64 = 3.0;
const BASE_FEE_RATE: f64 = 26.0 / 100.0;
const FEE_RATE_DEC_POWF: f64 = 1.15;
const UPD_PRICE_PROBA: f64 = 0.80;

// Buying 40000 worth of a resource will increase the price between 15% and 20%
const PRICE_INC_DIV: f64 = 40000.0;
const PRICE_INC_RANGE_MAX: f64 = 10.0 / 100.0;
const PRICE_INC_MIN_RATIO: f64 = 75.0 / 100.0;

#[inline]
pub fn fee_rate(rank: u8) -> f64 {
    BASE_FEE_RATE / (rank as f64).powf(FEE_RATE_DEC_POWF)
}

#[derive(Serialize)]
pub struct Market {
    pub prices: BTreeMap<Resource, f64>,
}

impl Market {
    pub fn init() -> Market {
        let mut prices = BTreeMap::new();
        for r in Resource::iter() {
            prices.insert(r, r.base_price());
        }
        Market { prices }
    }

    fn rand_distrib(&self, r: &Resource, now_price: f64) -> Normal<f64> {
        let base_price = r.base_price();
        let pratio = now_price / base_price;
        // 0.3    AVG = 1 - 0.3 = 0.7  * MAX AMPL = 3.5 * 0.7  =  2.45
        // 1.3    AVG = 1 - 1.3 = -0.3 * MAX AMPL = 3.5 * -0.3 = -1.05
        let avg = (1.0 - pratio) * MAX_AVG_AMPL;
        let std = avg.abs() + (MAX_AVG_AMPL / STD_DIV);

        rand_distr::Normal::new(avg, std).unwrap()
    }

    fn get_new_price<R: Rng>(&self, rng: &mut R, r: &Resource, old: f64) -> f64 {
        let distr = self.rand_distrib(r, old);
        let change = distr.sample(rng);
        old * (1.0 + change)
    }

    pub fn update_prices<R: Rng>(&mut self, rng: &mut R) {
        let mut new_prices = vec![];
        for (res, price) in self.prices.iter() {
            if !rng.random_bool(UPD_PRICE_PROBA) {
                continue;
            }

            new_prices.push((*res, self.get_new_price(rng, res, *price)));
        }

        for (r, price) in new_prices {
            let p = self.prices.get_mut(&r).unwrap();
            log::debug!("{r:?} {price} ({:?}%)", (price / r.base_price()) * 100.0);
            *p = price;
        }
    }

    pub fn buy(&mut self, trader: &CrewMember, r: &Resource, amnt: f64) -> MarketTx {
        assert!(amnt > 0.0);
        let fee_rate = fee_rate(trader.rank);

        let price = *self.prices.get(r).unwrap();
        assert!(price > 0.0);
        let cost = amnt * price;
        let fees = cost * fee_rate;
        let price_inc_max = (cost / PRICE_INC_DIV) * PRICE_INC_RANGE_MAX;
        let price_inc_min = price_inc_max * PRICE_INC_MIN_RATIO;
        let mut rng = rand::rng();
        let inc = rng.random_range(price_inc_min..=price_inc_max);
        *self.prices.get_mut(r).unwrap() *= 1.0 + inc;

        MarketTx {
            added_cargo: Some((*r, amnt)),
            removed_money: Some(cost + fees),
            fees,
            ..Default::default()
        }
    }

    pub fn sell(&mut self, trader: &CrewMember, r: &Resource, amnt: f64) -> MarketTx {
        assert!(amnt > 0.0);
        let fee_rate = fee_rate(trader.rank);

        let price = *self.prices.get(r).unwrap();
        assert!(price > 0.0);
        let cost = amnt * price;
        let fees = cost * fee_rate;

        let price_dec_max = (cost / PRICE_INC_DIV) * PRICE_INC_RANGE_MAX;
        let price_dec_min = price_dec_max * PRICE_INC_MIN_RATIO;
        let mut rng = rand::rng();
        let dec = rng.random_range(price_dec_min..=price_dec_max);
        *self.prices.get_mut(r).unwrap() *= 1.0 - dec;

        MarketTx {
            removed_cargo: Some((*r, amnt)),
            added_money: Some(cost - fees),
            fees,
            ..Default::default()
        }
    }
}

#[derive(Serialize, Deserialize, Default, Debug)]
pub struct MarketTx {
    pub added_cargo: Option<(Resource, f64)>,
    pub removed_cargo: Option<(Resource, f64)>,

    pub added_money: Option<f64>,
    pub removed_money: Option<f64>,
    pub fees: f64,
}
