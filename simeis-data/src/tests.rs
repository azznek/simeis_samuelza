use rand::{rngs::SmallRng, Rng, SeedableRng};

pub fn create_property_based_test<T: Fn(&mut SmallRng)>(niter: usize, reg: &[u64], f: T) {
    let mut seed_rng = rand::rng();
    for i in 0..niter {
        let seed = if let Some(seed) = reg.get(i) {
            *seed
        } else {
            seed_rng.random()
        };

        let mut rng = SmallRng::seed_from_u64(seed);
        println!("\n{i}/{niter}, seed {seed}");
        f(&mut rng);
    }
}
