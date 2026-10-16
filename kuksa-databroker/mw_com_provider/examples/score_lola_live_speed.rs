/********************************************************************************
 * Copyright (c) 2026 Contributors to the Eclipse Foundation
 *
 * See the NOTICE file(s) distributed with this work for additional
 * information regarding copyright ownership.
 *
 * This program and the accompanying materials are made available under the
 * terms of the Apache License Version 2.0 which is available at
 * https://www.apache.org/licenses/LICENSE-2.0
 *
 * SPDX-License-Identifier: Apache-2.0
 ********************************************************************************/

use databroker::broker::{ChangeType, DataBroker, DataType, DataValue, EntryType};
use databroker::permissions::ALLOW_ALL;
use mw_com_provider::score_bindings::{validate_score_bindings, ScoreBindingTransport};
use mw_com_provider::{LolaScoreRuntimeAdapter, MwComProvider, ProviderConfig};
use std::time::Duration;
use tokio::sync::oneshot;
use tokio::time::{sleep, timeout, Instant};

const SPEED_PATH: &str = "Vehicle.Speed";
const DEFAULT_EXPECTED_SAMPLES: usize = 25;

#[tokio::main(flavor = "current_thread")]
async fn main() -> Result<(), Box<dyn std::error::Error>> {
    println!("mw_com_provider live SCORE LoLa speed test");
    println!("===========================================");

    let score_config_path = std::env::var("SCORE_CONFIG_PATH")?;
    println!("SCORE_CONFIG_PATH={score_config_path}");
    let expected_samples = env_usize("SCORE_E2E_SAMPLE_COUNT", DEFAULT_EXPECTED_SAMPLES)?;
    let timeout_secs = env_u64("SCORE_E2E_TIMEOUT_SECS", 20)?;
    let poll_ms = env_u64("SCORE_E2E_POLL_MS", 10)?;
    println!("SCORE_E2E_SAMPLE_COUNT={expected_samples}");

    let mut config = ProviderConfig::load_json("generated/mw_com_provider_config.json")?;
    config
        .mappings
        .retain(|mapping| mapping.vss_path == SPEED_PATH);
    validate_score_bindings(&config)?;

    let broker = DataBroker::new("score-lola-live-speed", "score-lola-live-speed");
    let speed_id = broker
        .authorized_access(&ALLOW_ALL)
        .add_entry(
            SPEED_PATH.into(),
            DataType::Double,
            ChangeType::Continuous,
            EntryType::Sensor,
            "Live SCORE LoLa speed signal".into(),
            None,
            None,
            None,
            None,
        )
        .await
        .map_err(|error| format!("failed to register {SPEED_PATH}: {error:?}"))?;

    for mapping in &mut config.mappings {
        mapping.signal_id = speed_id;
    }

    let adapter = LolaScoreRuntimeAdapter::from_score_config_env()?;
    let transport = ScoreBindingTransport::new(adapter);
    let provider = MwComProvider::new(broker.clone(), ALLOW_ALL.clone(), config, transport)?;

    provider.register_with_broker().await?;
    let (shutdown_tx, shutdown_rx) = oneshot::channel();
    let provider_task = tokio::spawn(async move { provider.run_until_shutdown(shutdown_rx).await });

    let observed =
        wait_for_speed_samples(&broker, speed_id, expected_samples, timeout_secs, poll_ms).await?;
    if let Some(final_value) = observed.last() {
        println!("Vehicle.Speed reached Databroker from live SCORE LoLa: {final_value:.3} km/h");
    }
    if observed.len() > 1 {
        println!("Vehicle.Speed changed samples observed: {observed:?}");
    }

    let _ = shutdown_tx.send(());
    timeout(Duration::from_secs(2), provider_task).await???;

    println!("Live SCORE LoLa speed test completed successfully.");
    Ok(())
}

async fn wait_for_speed_samples(
    broker: &DataBroker,
    signal_id: i32,
    expected_samples: usize,
    timeout_secs: u64,
    poll_ms: u64,
) -> Result<Vec<f64>, Box<dyn std::error::Error>> {
    let deadline = Instant::now() + Duration::from_secs(timeout_secs);
    let mut last_value = None;
    let mut observed = Vec::with_capacity(expected_samples);

    loop {
        let datapoint = broker
            .authorized_access(&ALLOW_ALL)
            .get_datapoint(signal_id)
            .await
            .map_err(|error| format!("failed to read {SPEED_PATH}: {error:?}"))?;
        if last_value.as_ref() != Some(&datapoint.value) {
            println!("Databroker observed value: {:?}", datapoint.value);
            if let DataValue::Double(value) = datapoint.value.clone() {
                if value > 0.0 {
                    observed.push(value);
                    if observed.len() >= expected_samples {
                        return Ok(observed);
                    }
                }
            }
            last_value = Some(datapoint.value.clone());
        }

        if Instant::now() >= deadline {
            return Err(format!(
                "timed out waiting for {expected_samples} changed live SCORE LoLa speed sample(s); observed {}",
                observed.len()
            )
            .into());
        }
        sleep(Duration::from_millis(poll_ms)).await;
    }
}

fn env_usize(name: &str, default: usize) -> Result<usize, Box<dyn std::error::Error>> {
    let value = match std::env::var(name) {
        Ok(value) => value.parse::<usize>()?,
        Err(std::env::VarError::NotPresent) => default,
        Err(error) => return Err(Box::new(error)),
    };
    if value == 0 {
        Err(format!("{name} must be greater than zero").into())
    } else {
        Ok(value)
    }
}

fn env_u64(name: &str, default: u64) -> Result<u64, Box<dyn std::error::Error>> {
    let value = match std::env::var(name) {
        Ok(value) => value.parse::<u64>()?,
        Err(std::env::VarError::NotPresent) => default,
        Err(error) => return Err(Box::new(error)),
    };
    if value == 0 {
        Err(format!("{name} must be greater than zero").into())
    } else {
        Ok(value)
    }
}
