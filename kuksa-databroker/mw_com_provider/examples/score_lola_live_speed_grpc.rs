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

use databroker::authorization::Authorization;
use databroker::broker::{ChangeType, DataBroker, DataType, EntryType};
use databroker::grpc::server::{self, Api};
use databroker::permissions::ALLOW_ALL;
use databroker_proto::kuksa::val::v2::{
    signal_id, val_client::ValClient, value, GetValuesRequest, SignalId,
};
use mw_com_provider::score_bindings::{validate_score_bindings, ScoreBindingTransport};
use mw_com_provider::{LolaScoreRuntimeAdapter, MwComProvider, ProviderConfig};
use std::net::SocketAddr;
use std::time::Duration;
use tokio::sync::oneshot;
use tokio::time::{sleep, timeout, Instant};

const SPEED_PATH: &str = "Vehicle.Speed";
const DEFAULT_EXPECTED_SAMPLES: usize = 25;

#[tokio::main(flavor = "current_thread")]
async fn main() -> Result<(), Box<dyn std::error::Error>> {
    println!("mw_com_provider live SCORE LoLa speed gRPC test");
    println!("================================================");

    let score_config_path = std::env::var("SCORE_CONFIG_PATH")?;
    println!("SCORE_CONFIG_PATH={score_config_path}");
    let expected_samples = env_usize("SCORE_E2E_SAMPLE_COUNT", DEFAULT_EXPECTED_SAMPLES)?;
    let timeout_secs = env_u64("SCORE_E2E_TIMEOUT_SECS", 60)?;
    let poll_ms = env_u64("SCORE_E2E_POLL_MS", 10)?;
    let grpc_addr = env_socket_addr("DATABROKER_GRPC_ADDR", "127.0.0.1:55555")?;
    let grpc_endpoint = format!("http://{grpc_addr}");
    println!("SCORE_E2E_SAMPLE_COUNT={expected_samples}");
    println!("DATABROKER_GRPC_ENDPOINT={grpc_endpoint}");

    let mut config = ProviderConfig::load_json("generated/mw_com_provider_config.json")?;
    config
        .mappings
        .retain(|mapping| mapping.vss_path == SPEED_PATH);
    validate_score_bindings(&config)?;

    let broker = DataBroker::new("score-lola-live-speed-grpc", "score-lola-live-speed-grpc");
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

    let (grpc_shutdown_tx, grpc_shutdown_rx) = oneshot::channel();
    let grpc_broker = broker.clone();
    let grpc_task = tokio::spawn(async move {
        server::serve_tcp(
            grpc_addr,
            grpc_broker,
            &[Api::KuksaValV2],
            Authorization::Disabled,
            async move {
                let _ = grpc_shutdown_rx.await;
            },
        )
        .await
        .map_err(|error| error.to_string())
    });

    let adapter = LolaScoreRuntimeAdapter::from_score_config_env()?;
    let transport = ScoreBindingTransport::new(adapter);
    let provider = MwComProvider::new(broker, ALLOW_ALL.clone(), config, transport)?;

    provider.register_with_broker().await?;
    let (provider_shutdown_tx, provider_shutdown_rx) = oneshot::channel();
    let provider_task =
        tokio::spawn(async move { provider.run_until_shutdown(provider_shutdown_rx).await });

    let observed =
        wait_for_speed_samples_grpc(&grpc_endpoint, expected_samples, timeout_secs, poll_ms)
            .await?;
    if let Some(final_value) = observed.last() {
        println!(
            "Vehicle.Speed reached Databroker gRPC API from live SCORE LoLa: {final_value:.3} km/h"
        );
    }
    if observed.len() > 1 {
        println!("Vehicle.Speed changed samples observed through gRPC: {observed:?}");
    }

    let _ = provider_shutdown_tx.send(());
    timeout(Duration::from_secs(2), provider_task).await???;
    let _ = grpc_shutdown_tx.send(());
    timeout(Duration::from_secs(2), grpc_task).await???;

    println!("Live SCORE LoLa speed gRPC test completed successfully.");
    Ok(())
}

async fn wait_for_speed_samples_grpc(
    grpc_endpoint: &str,
    expected_samples: usize,
    timeout_secs: u64,
    poll_ms: u64,
) -> Result<Vec<f64>, Box<dyn std::error::Error>> {
    let deadline = Instant::now() + Duration::from_secs(timeout_secs);
    let mut client = None;
    let mut last_value = None;
    let mut observed = Vec::with_capacity(expected_samples);

    loop {
        if client.is_none() {
            match ValClient::connect(grpc_endpoint.to_owned()).await {
                Ok(connected) => client = Some(connected),
                Err(error) => {
                    if Instant::now() >= deadline {
                        return Err(format!(
                            "timed out connecting to Databroker gRPC endpoint {grpc_endpoint}: {error}"
                        )
                        .into());
                    }
                    sleep(Duration::from_millis(poll_ms)).await;
                    continue;
                }
            }
        }

        let request = GetValuesRequest {
            signal_ids: vec![SignalId {
                signal: Some(signal_id::Signal::Path(SPEED_PATH.to_owned())),
            }],
        };
        let response = client
            .as_mut()
            .expect("gRPC client is connected")
            .get_values(request)
            .await?
            .into_inner();
        let value = response
            .data_points
            .first()
            .and_then(|datapoint| datapoint.value.as_ref())
            .and_then(|value| value.typed_value.as_ref());

        if last_value.as_ref() != Some(&value.cloned()) {
            println!("Databroker gRPC observed value: {value:?}");
            if let Some(value::TypedValue::Double(value)) = value {
                if *value > 0.0 {
                    observed.push(*value);
                    if observed.len() >= expected_samples {
                        return Ok(observed);
                    }
                }
            }
            last_value = Some(value.cloned());
        }

        if Instant::now() >= deadline {
            return Err(format!(
                "timed out waiting for {expected_samples} changed live SCORE LoLa speed sample(s) through gRPC; observed {}",
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

fn env_socket_addr(name: &str, default: &str) -> Result<SocketAddr, Box<dyn std::error::Error>> {
    let value = match std::env::var(name) {
        Ok(value) => value,
        Err(std::env::VarError::NotPresent) => default.to_owned(),
        Err(error) => return Err(Box::new(error)),
    };
    Ok(value.parse()?)
}
