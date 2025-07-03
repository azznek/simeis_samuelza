#![allow(unexpected_cfgs)]
use ntex::web;

use simeis_data::game::Game;

mod api;

pub type GameState = ntex::web::types::State<Game>;

#[ntex::main]
async fn main() -> std::io::Result<()> {
    std::env::set_var("RUST_LOG", "debug");
    #[cfg(not(feature = "testing"))]
    let port = 8080;

    #[cfg(feature = "testing")]
    let port = 9345;

    env_logger::builder()
        .parse_default_env()
        .filter_module("ntex_server", log::LevelFilter::Warn)
        .filter_module("ntex_io", log::LevelFilter::Warn)
        .filter_module("ntex_rt", log::LevelFilter::Warn)
        .filter_module("ntex::http::h1", log::LevelFilter::Warn)
        .init();

    log::info!("Running on http://0.0.0.0:{port}");
    let (gamethread, state) = Game::init();
    let game = state.clone();

    let res = web::HttpServer::new(move || {
        web::App::new()
            .wrap(web::middleware::Logger::default())
            .state(state.clone())
            .configure(api::configure)
    })
    .stop_runtime()
    .bind(("0.0.0.0", port))?
    .run()
    .await;

    game.stop(gamethread).await;
    res
}

#[cfg(feature = "heavy_testing")]
#[test]
fn test_heavy_testing() {
    assert!(false);
}
