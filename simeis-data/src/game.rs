use base64::{prelude::BASE64_STANDARD, Engine};
use std::collections::{BTreeMap, HashMap};
use std::sync::Arc;
use std::time::{Duration, Instant};
use tokio::sync::mpsc::{Receiver, Sender};
use tokio::sync::RwLock;
use tokio::task::JoinHandle;

#[cfg(not(feature = "testing"))]
use tokio::sync::mpsc::error::TryRecvError;

use rand::{Rng, SeedableRng};

use crate::errors::Errcode;
use crate::galaxy::Galaxy;
use crate::market::{Market, MARKET_CHANGE_SEC};
use crate::player::{Player, PlayerId, PlayerKey};
use crate::ship::ShipState;
use crate::syslog::{SyslogEvent, SyslogFifo, SyslogRecv, SyslogSend};

const ITER_PERIOD: Duration = Duration::from_millis(20);

// TODO (#23) Have a global "inflation" rate for all users, that increases over time
//     Equipment becomes more and more expansive

pub enum GameSignal {
    Stop,
    Tick,
}

#[derive(Clone)]
pub struct Game {
    pub players: Arc<RwLock<BTreeMap<PlayerId, Arc<RwLock<Player>>>>>,
    pub player_index: Arc<RwLock<HashMap<PlayerKey, PlayerId>>>,
    pub galaxy: Arc<RwLock<Galaxy>>,
    pub market: Arc<RwLock<Market>>,
    pub syslog: SyslogSend,
    pub fifo_events: SyslogFifo,
    pub tstart: f64,
    pub send_sig: Sender<GameSignal>,
}

impl Game {
    pub fn init() -> (JoinHandle<()>, Game) {
        let (send_stop, recv_stop) = tokio::sync::mpsc::channel(5);
        let (syssend, sysrecv) = SyslogSend::channel();
        let tstart = std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .unwrap()
            .as_secs_f64();
        let data = Game {
            send_sig: send_stop,
            galaxy: Arc::new(RwLock::new(Galaxy::init())),
            market: Arc::new(RwLock::new(Market::init())),
            players: Arc::new(RwLock::new(BTreeMap::new())),
            player_index: Arc::new(RwLock::new(HashMap::new())),
            syslog: syssend.clone(),
            fifo_events: sysrecv.fifo.clone(),
            tstart,
        };

        let thread_data = data.clone();
        // TODO Reduce stack size of this task
        let thread = tokio::spawn(async move { thread_data.start(recv_stop, sysrecv).await });
        (thread, data)
    }

    #[allow(unused_variables, unused_mut)]
    pub async fn start(&self, mut stop: Receiver<GameSignal>, syslog: SyslogRecv) {
        log::debug!("Started thread");
        let sleepmin_iter = ITER_PERIOD;
        let mut last_iter = Instant::now();
        let mut market_last_tick = Instant::now();
        let mut rng = rand::rngs::SmallRng::from_os_rng();

        'main: loop {
            #[cfg(feature = "testing")]
            let got = stop.recv().await;

            #[cfg(not(feature = "testing"))]
            let got = match stop.try_recv() {
                Ok(res) => Some(res),
                Err(TryRecvError::Empty) => Some(GameSignal::Tick),
                Err(e) => {
                    log::error!("Error while getting next tick / stop signal:  {e:?}");
                    None
                }
            };

            match got {
                Some(GameSignal::Tick) => {
                    self.threadloop(&mut rng, &mut market_last_tick, &syslog)
                        .await;

                    #[cfg(not(feature = "testing"))]
                    {
                        let took = Instant::now() - last_iter;
                        tokio::time::sleep(sleepmin_iter.saturating_sub(took)).await;
                        last_iter = Instant::now();
                    }
                }

                None | Some(GameSignal::Stop) => break 'main,
            }
        }
        log::info!("Exiting game thread");
    }

    async fn threadloop<R: Rng>(&self, rng: &mut R, mlt: &mut Instant, syslog: &SyslogRecv) {
        let market_change_proba = (mlt.elapsed().as_secs_f64() / MARKET_CHANGE_SEC).min(1.0);

        // OK
        let players = self.players.read().await;
        let mut all_players: Vec<PlayerId> = players.keys().cloned().collect();
        all_players.sort();
        for player_id in all_players {
            let mut player = players.get(&player_id).unwrap().write().await; // OK
            player.update_money(syslog, ITER_PERIOD.as_secs_f64()).await;

            let mut deadship = vec![];
            for (id, ship) in player.ships.iter_mut() {
                match ship.state {
                    ShipState::InFlight(..) => {
                        let finished = ship.update_flight(ITER_PERIOD.as_secs_f64());
                        if finished {
                            ship.state = ShipState::Idle;
                            if ship.hull_decay >= ship.hull_decay_capacity {
                                deadship.push(*id);
                            } else {
                                syslog
                                    .event(player_id, SyslogEvent::ShipFlightFinished(*id))
                                    .await;
                            }
                        }
                    }

                    ShipState::Extracting(..) => {
                        let finished = ship.update_extract(ITER_PERIOD.as_secs_f64());
                        if finished {
                            ship.state = ShipState::Idle;
                            syslog
                                .event(player_id, SyslogEvent::ExtractionStopped(*id))
                                .await;
                        }
                    }
                    _ => {}
                }
            }
            for id in deadship {
                syslog
                    .event(player_id, SyslogEvent::ShipDestroyed(id))
                    .await;
                player.ships.remove(&id);
            }
        }

        if rng.random_bool(market_change_proba) {
            #[cfg(not(feature = "testing"))]
            self.market.write().await.update_prices(rng); // OK
            *mlt = Instant::now();
        }

        syslog.update().await;
    }

    pub async fn stop(self, handle: JoinHandle<()>) {
        log::info!("Asking game thread to exit");
        self.send_sig.send(GameSignal::Stop).await.unwrap();
        let _ = handle.await;
        log::info!("Game stopped");
    }

    pub async fn new_player(&self, name: String) -> Result<(PlayerId, String), Errcode> {
        let mut index = self.player_index.write().await;
        let mut players = self.players.write().await;
        let mut galaxy = self.galaxy.write().await;
        let station = galaxy.init_new_station().await;

        let player = Player::new(station, name);
        let pid = player.id;
        let key = BASE64_STANDARD.encode(player.key);

        index.insert(player.key, player.id);
        players.insert(player.id, Arc::new(RwLock::new(player)));
        self.syslog.event(&pid, SyslogEvent::GameStarted).await;
        Ok((pid, key))
    }
}
