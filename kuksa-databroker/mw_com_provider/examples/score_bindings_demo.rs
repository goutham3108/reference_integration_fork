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

use async_trait::async_trait;
use databroker::broker::{ChangeType, DataBroker, DataType, DataValue, EntryType};
use databroker::permissions::ALLOW_ALL;
use mw_com_provider::score_bindings::{
    generated_score_bindings, validate_score_bindings, ScoreBinding, ScoreBindingTransport,
    ScoreRuntimeAdapter,
};
use mw_com_provider::{
    MwComMessage, MwComProvider, MwComProviderError, MwComValue, ProviderConfig,
};
use std::time::{Duration, SystemTime};
use tokio::sync::{mpsc, oneshot};
use tokio::time::timeout;

struct DemoScoreApplication {
    inbound: mpsc::Sender<MwComMessage>,
    outbound: mpsc::Receiver<MwComMessage>,
}

impl DemoScoreApplication {
    fn new() -> (Self, DemoScoreRuntimeAdapter) {
        let (inbound_tx, inbound_rx) = mpsc::channel(8);
        let (outbound_tx, outbound_rx) = mpsc::channel(8);

        (
            Self {
                inbound: inbound_tx,
                outbound: outbound_rx,
            },
            DemoScoreRuntimeAdapter {
                inbound: inbound_rx,
                outbound: outbound_tx,
                connected: false,
            },
        )
    }

    async fn publish_speed(&self, speed: f64) {
        self.inbound
            .send(MwComMessage {
                service: "VehicleDynamicsService".into(),
                instance: "front_vehicle".into(),
                member: "speed".into(),
                value: MwComValue::F64(speed),
                source_timestamp: Some(SystemTime::now()),
                quality: mw_com_provider::SignalQuality::Valid,
            })
            .await
            .expect("demo SCORE inbound channel should be open");
    }

    async fn next_actuation(&mut self) -> MwComMessage {
        let message = timeout(Duration::from_secs(1), self.outbound.recv())
            .await
            .expect("timed out waiting for SCORE actuation")
            .expect("demo SCORE outbound channel should be open");
        message
    }
}

struct DemoScoreRuntimeAdapter {
    inbound: mpsc::Receiver<MwComMessage>,
    outbound: mpsc::Sender<MwComMessage>,
    connected: bool,
}

#[async_trait]
impl ScoreRuntimeAdapter for DemoScoreRuntimeAdapter {
    async fn connect(&mut self) -> Result<(), MwComProviderError> {
        self.connected = true;
        println!("SCORE adapter: connected to demo runtime");
        Ok(())
    }

    async fn disconnect(&mut self) -> Result<(), MwComProviderError> {
        self.connected = false;
        println!("SCORE adapter: disconnected");
        Ok(())
    }

    async fn find_service(&self, binding: ScoreBinding<'_>) -> Result<bool, MwComProviderError> {
        println!(
            "SCORE adapter: found service={} instance_specifier={} member={}",
            binding.service_name, binding.instance_specifier, binding.member_name
        );
        Ok(self.connected)
    }

    async fn subscribe(&mut self, binding: ScoreBinding<'_>) -> Result<(), MwComProviderError> {
        println!(
            "SCORE adapter: subscribed to {}:{} ({})",
            binding.service_name, binding.member_name, binding.payload_type
        );
        Ok(())
    }

    async fn unsubscribe(&mut self, binding: ScoreBinding<'_>) -> Result<(), MwComProviderError> {
        println!(
            "SCORE adapter: unsubscribed from {}:{}",
            binding.service_name, binding.member_name
        );
        Ok(())
    }

    async fn recv(&mut self) -> Result<Option<MwComMessage>, MwComProviderError> {
        let message = match timeout(Duration::from_millis(25), self.inbound.recv()).await {
            Ok(message) => message,
            Err(_) => return Ok(None),
        };
        if let Some(message) = &message {
            println!(
                "SCORE adapter: received sample {}:{} value={:?}",
                message.service, message.member, message.value
            );
        }
        Ok(message)
    }

    async fn send_actuation(
        &mut self,
        binding: ScoreBinding<'_>,
        message: MwComMessage,
    ) -> Result<(), MwComProviderError> {
        println!(
            "SCORE adapter: publishing actuation to {}:{} ({})",
            binding.service_name, binding.member_name, binding.payload_type
        );
        self.outbound.send(message).await.map_err(|_| {
            MwComProviderError::Transport("demo SCORE outbound receiver dropped".into())
        })
    }
}

#[tokio::main(flavor = "current_thread")]
async fn main() -> Result<(), Box<dyn std::error::Error>> {
    println!("mw_com_provider SCORE binding demo");
    println!("==================================");

    println!("\nGenerated SCORE bindings:");
    for binding in generated_score_bindings() {
        println!(
            "  {}:{} -> {} member={} payload={}",
            binding.service_name,
            binding.instance_name,
            binding.instance_specifier,
            binding.member_name,
            binding.payload_type
        );
    }

    let mut config = ProviderConfig::load_json("generated/mw_com_provider_config.json")?;

    let broker = DataBroker::new("score-binding-demo", "score-binding-demo");
    let speed_id = add_vss_entry(
        &broker,
        "Vehicle.Speed",
        DataType::Double,
        EntryType::Sensor,
    )
    .await;
    let target_speed_id = add_vss_entry(
        &broker,
        "Vehicle.ADAS.CruiseControl.TargetSpeed",
        DataType::Double,
        EntryType::Actuator,
    )
    .await;
    let enabled_id = add_vss_entry(
        &broker,
        "Vehicle.ADAS.CruiseControl.IsEnabled",
        DataType::Bool,
        EntryType::Actuator,
    )
    .await;
    for mapping in &mut config.mappings {
        mapping.signal_id = match mapping.vss_path.as_str() {
            "Vehicle.Speed" => speed_id,
            "Vehicle.ADAS.CruiseControl.TargetSpeed" => target_speed_id,
            "Vehicle.ADAS.CruiseControl.IsEnabled" => enabled_id,
            other => return Err(format!("demo does not register VSS path {other}").into()),
        };
    }
    validate_score_bindings(&config)?;

    let (mut score_app, adapter) = DemoScoreApplication::new();
    let transport = ScoreBindingTransport::new(adapter);
    let provider = MwComProvider::new(broker.clone(), ALLOW_ALL.clone(), config, transport)?;

    provider.register_with_broker().await?;
    let (shutdown_tx, shutdown_rx) = oneshot::channel();
    let provider_task = tokio::spawn(async move { provider.run_until_shutdown(shutdown_rx).await });

    println!("\nSCORE -> provider -> Databroker:");
    score_app.publish_speed(27.5).await;
    wait_for_double_datapoint(&broker, speed_id, 99.0).await;
    println!("  Vehicle.Speed updated to 99.0 km/h from SCORE speed sample 27.5 m/s");

    println!("\nDatabroker -> provider -> SCORE:");
    broker
        .authorized_access(&ALLOW_ALL)
        .actuate(&target_speed_id, &DataValue::Double(72.0))
        .await
        .map_err(|error| format!("target speed actuation failed: {error:?}"))?;
    let target_speed = score_app.next_actuation().await;
    println!(
        "  target_speed actuation reached SCORE as {:?}",
        target_speed.value
    );

    broker
        .authorized_access(&ALLOW_ALL)
        .actuate(&enabled_id, &DataValue::Bool(true))
        .await
        .map_err(|error| format!("enabled actuation failed: {error:?}"))?;
    let enabled = score_app.next_actuation().await;
    println!(
        "  cruise_control_enabled actuation reached SCORE as {:?}",
        enabled.value
    );

    shutdown_tx
        .send(())
        .expect("provider demo shutdown channel should be open");
    timeout(Duration::from_secs(1), provider_task)
        .await??
        .expect("provider should shut down cleanly");

    println!("\nDemo completed successfully.");
    Ok(())
}

async fn add_vss_entry(
    broker: &DataBroker,
    path: &str,
    data_type: DataType,
    entry_type: EntryType,
) -> i32 {
    broker
        .authorized_access(&ALLOW_ALL)
        .add_entry(
            path.into(),
            data_type,
            ChangeType::Continuous,
            entry_type,
            format!("Demo metadata for {path}"),
            None,
            None,
            None,
            None,
        )
        .await
        .expect("demo VSS metadata should register")
}

async fn wait_for_double_datapoint(broker: &DataBroker, signal_id: i32, expected: f64) {
    timeout(Duration::from_secs(2), async {
        let mut last_value = None;
        loop {
            let datapoint = broker
                .authorized_access(&ALLOW_ALL)
                .get_datapoint(signal_id)
                .await
                .expect("demo datapoint should exist");
            if last_value.as_ref() != Some(&datapoint.value) {
                println!("  Databroker observed value: {:?}", datapoint.value);
                last_value = Some(datapoint.value.clone());
            }
            if matches!(datapoint.value, DataValue::Double(actual) if (actual - expected).abs() < 0.000_001) {
                return;
            }
            tokio::task::yield_now().await;
        }
    })
    .await
    .expect("timed out waiting for Databroker datapoint");
}
