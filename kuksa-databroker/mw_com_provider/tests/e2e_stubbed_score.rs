#![cfg(feature = "mock-transport")]

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
use mw_com_provider::transport::mock::MockMwComTransport;
use mw_com_provider::{
    Direction, MwComMessage, MwComProvider, MwComValue, ProviderConfig, SignalMapping,
    SignalQuality, VssDataType,
};
use std::time::{Duration, SystemTime};
use tokio::sync::{mpsc, oneshot};
use tokio::time::timeout;

struct StubbedScoreMwComApplication {
    inbound: mpsc::Sender<MwComMessage>,
    outbound: mpsc::Receiver<MwComMessage>,
}

impl StubbedScoreMwComApplication {
    fn new() -> (Self, MockMwComTransport) {
        let (inbound_tx, inbound_rx) = mpsc::channel(4);
        let (outbound_tx, outbound_rx) = mpsc::channel(4);

        (
            Self {
                inbound: inbound_tx,
                outbound: outbound_rx,
            },
            MockMwComTransport::new(inbound_rx, outbound_tx),
        )
    }

    async fn publish_speed_sample(&self, speed: f64) {
        self.inbound
            .send(MwComMessage {
                service: "VehicleDynamicsService".into(),
                instance: "front_vehicle".into(),
                member: "speed".into(),
                value: MwComValue::F64(speed),
                source_timestamp: Some(SystemTime::now()),
                quality: SignalQuality::Valid,
            })
            .await
            .unwrap();
    }

    async fn next_actuation(&mut self) -> MwComMessage {
        timeout(Duration::from_secs(1), self.outbound.recv())
            .await
            .unwrap()
            .unwrap()
    }
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
            format!("Test metadata for {path}"),
            None,
            None,
            None,
            None,
        )
        .await
        .unwrap()
}

fn mapping(
    signal_id: i32,
    vss_path: &str,
    member: &str,
    direction: Direction,
    datatype: VssDataType,
) -> SignalMapping {
    SignalMapping {
        signal_id,
        vss_path: vss_path.into(),
        datatype,
        service: "VehicleDynamicsService".into(),
        instance: "front_vehicle".into(),
        member: member.into(),
        actuation_binding: None,
        field: None,
        unit: None,
        scale: 1.0,
        offset: 0.0,
        min: None,
        max: None,
        required_quality: SignalQuality::Valid,
        direction,
        cycle_time_ms: 100,
    }
}

fn provider_config(speed_id: i32, target_speed_id: i32) -> ProviderConfig {
    ProviderConfig {
        provider_name: "stubbed_score_e2e".into(),
        reconnect: Default::default(),
        queue_capacity: 4,
        stale_after_ms: 1_000,
        mappings: vec![
            mapping(
                speed_id,
                "Vehicle.Speed",
                "speed",
                Direction::Datapoint,
                VssDataType::Double,
            ),
            mapping(
                target_speed_id,
                "Vehicle.ADAS.CruiseControl.TargetSpeed",
                "targetSpeed",
                Direction::Actuator,
                VssDataType::Double,
            ),
        ],
    }
}

async fn setup_provider() -> (
    DataBroker,
    MwComProvider,
    StubbedScoreMwComApplication,
    i32,
    i32,
) {
    let broker = DataBroker::new("test", "test");
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
    let (stubbed_score_app, transport) = StubbedScoreMwComApplication::new();
    let provider = MwComProvider::new(
        broker.clone(),
        ALLOW_ALL.clone(),
        provider_config(speed_id, target_speed_id),
        transport,
    )
    .unwrap();

    (
        broker,
        provider,
        stubbed_score_app,
        speed_id,
        target_speed_id,
    )
}

async fn wait_for_datapoint(broker: &DataBroker, signal_id: i32, expected: DataValue) {
    timeout(Duration::from_secs(1), async {
        loop {
            let datapoint = broker
                .authorized_access(&ALLOW_ALL)
                .get_datapoint(signal_id)
                .await
                .unwrap();
            if datapoint.value == expected {
                return;
            }
            tokio::task::yield_now().await;
        }
    })
    .await
    .unwrap();
}

#[tokio::test]
async fn stubbed_score_sample_updates_databroker_vss_datapoint() {
    let (broker, provider, stubbed_score_app, speed_id, _target_speed_id) = setup_provider().await;
    provider.register_with_broker().await.unwrap();
    let (shutdown_tx, shutdown_rx) = oneshot::channel();
    let provider_task = tokio::spawn(async move { provider.run_until_shutdown(shutdown_rx).await });

    stubbed_score_app.publish_speed_sample(88.5).await;
    wait_for_datapoint(&broker, speed_id, DataValue::Double(88.5)).await;

    shutdown_tx.send(()).unwrap();
    timeout(Duration::from_secs(1), provider_task)
        .await
        .unwrap()
        .unwrap()
        .unwrap();
}

#[tokio::test]
async fn databroker_actuation_reaches_stubbed_score_application() {
    let (broker, provider, mut stubbed_score_app, _speed_id, target_speed_id) =
        setup_provider().await;
    provider.register_with_broker().await.unwrap();

    broker
        .authorized_access(&ALLOW_ALL)
        .actuate(&target_speed_id, &DataValue::Double(72.0))
        .await
        .unwrap();
    let message = stubbed_score_app.next_actuation().await;

    assert_eq!(message.service, "VehicleDynamicsService");
    assert_eq!(message.instance, "front_vehicle");
    assert_eq!(message.member, "targetSpeed");
    assert_eq!(message.value, MwComValue::F64(72.0));
}

#[tokio::test]
async fn beam_worker_actuates_and_receives_independent_high_and_low_feedback() {
    let broker = DataBroker::new("test", "test");
    let id = add_vss_entry(
        &broker,
        "Vehicle.Body.Lights.Beam.High.IsOn",
        DataType::Bool,
        EntryType::Actuator,
    )
    .await;
    let mut signal = mapping(
        id,
        "Vehicle.Body.Lights.Beam.High.IsOn",
        "high_beam_state",
        Direction::Bidirectional,
        VssDataType::Bool,
    );
    signal.service = "/vehicle_high_beam_rx".into();
    signal.instance = "network_rx".into();
    signal.actuation_binding = Some(mw_com_provider::config::ActuationBinding {
        service: "/vehicle_high_beam_tx".into(),
        instance: "local_tx".into(),
        member: "high_beam_state".into(),
    });
    let output_id = add_vss_entry(
        &broker,
        "Vehicle.Body.Lights.Beam.Low.IsOn",
        DataType::Bool,
        EntryType::Actuator,
    )
    .await;
    let mut output = mapping(
        output_id,
        "Vehicle.Body.Lights.Beam.Low.IsOn",
        "low_beam_state",
        Direction::Bidirectional,
        VssDataType::Bool,
    );
    output.service = "/vehicle_high_beam_rx".into();
    output.instance = "network_rx".into();
    output.actuation_binding = Some(mw_com_provider::config::ActuationBinding {
        service: "/vehicle_high_beam_tx".into(),
        instance: "local_tx".into(),
        member: "low_beam_state".into(),
    });
    let config = ProviderConfig {
        provider_name: "high_beam_test".into(),
        reconnect: Default::default(),
        queue_capacity: 4,
        stale_after_ms: 1000,
        mappings: vec![signal, output],
    };
    let (mut app, transport) = StubbedScoreMwComApplication::new();
    let worker = mw_com_provider::MwComProviderWorker::new(
        broker.clone(),
        ALLOW_ALL.clone(),
        config,
        transport,
    )
    .unwrap();
    worker.register_with_broker().await.unwrap();
    let (shutdown_tx, shutdown_rx) = oneshot::channel();
    let task = tokio::spawn(worker.run_until_shutdown(shutdown_rx));
    app.inbound
        .send(MwComMessage {
            service: "/vehicle_high_beam_rx".into(),
            instance: "network_rx".into(),
            member: "high_beam_state".into(),
            value: MwComValue::Bool(true),
            source_timestamp: Some(SystemTime::now()),
            quality: SignalQuality::Valid,
        })
        .await
        .unwrap();
    wait_for_datapoint(&broker, id, DataValue::Bool(true)).await;
    app.inbound
        .send(MwComMessage {
            service: "/vehicle_high_beam_rx".into(),
            instance: "network_rx".into(),
            member: "low_beam_state".into(),
            value: MwComValue::Bool(false),
            source_timestamp: Some(SystemTime::now()),
            quality: SignalQuality::Valid,
        })
        .await
        .unwrap();
    wait_for_datapoint(&broker, output_id, DataValue::Bool(false)).await;
    use databroker_proto::kuksa::val::v2 as val;
    use databroker_proto::sdv::databroker::v1 as vdb;
    for (path, signal_id, member, other_id) in [
        (
            "Vehicle.Body.Lights.Beam.High.IsOn",
            id,
            "high_beam_state",
            output_id,
        ),
        (
            "Vehicle.Body.Lights.Beam.Low.IsOn",
            output_id,
            "low_beam_state",
            id,
        ),
    ] {
        for desired_on in [true, false, true] {
            let previous = broker
                .authorized_access(&ALLOW_ALL)
                .get_datapoint(signal_id)
                .await
                .unwrap()
                .value;
            let other = broker
                .authorized_access(&ALLOW_ALL)
                .get_datapoint(other_id)
                .await
                .unwrap()
                .value;
            let mut request = tonic::Request::new(vdb::SetDatapointsRequest {
                datapoints: [(
                    path.into(),
                    vdb::Datapoint {
                        timestamp: None,
                        value: Some(vdb::datapoint::Value::BoolValue(desired_on)),
                    },
                )]
                .into_iter()
                .collect(),
            });
            request.extensions_mut().insert(ALLOW_ALL.clone());
            let reply = vdb::broker_server::Broker::set_datapoints(&broker, request)
                .await
                .unwrap()
                .into_inner();
            assert!(reply.errors.is_empty());
            let sent = app.next_actuation().await;
            assert_eq!(sent.service, "/vehicle_high_beam_tx");
            assert_eq!(sent.instance, "local_tx");
            assert_eq!(sent.member, member);
            assert_eq!(sent.value, MwComValue::Bool(desired_on));
            assert_eq!(
                broker
                    .authorized_access(&ALLOW_ALL)
                    .get_datapoint(signal_id)
                    .await
                    .unwrap()
                    .value,
                previous
            );
            app.inbound
                .send(MwComMessage {
                    service: "/vehicle_high_beam_rx".into(),
                    instance: "network_rx".into(),
                    member: member.into(),
                    value: MwComValue::Bool(desired_on),
                    source_timestamp: Some(SystemTime::now()),
                    quality: SignalQuality::Valid,
                })
                .await
                .unwrap();
            wait_for_datapoint(&broker, signal_id, DataValue::Bool(desired_on)).await;
            assert_eq!(
                broker
                    .authorized_access(&ALLOW_ALL)
                    .get_datapoint(other_id)
                    .await
                    .unwrap()
                    .value,
                other
            );
        }
    }
    for (path, signal_id, member) in [
        ("Vehicle.Body.Lights.Beam.High.IsOn", id, "high_beam_state"),
        (
            "Vehicle.Body.Lights.Beam.Low.IsOn",
            output_id,
            "low_beam_state",
        ),
    ] {
        let mut request = tonic::Request::new(val::ActuateRequest {
            signal_id: Some(val::SignalId {
                signal: Some(val::signal_id::Signal::Path(path.into())),
            }),
            value: Some(val::Value {
                typed_value: Some(val::value::TypedValue::Bool(false)),
            }),
        });
        request.extensions_mut().insert(ALLOW_ALL.clone());
        val::val_server::Val::actuate(&broker, request)
            .await
            .unwrap();
        let sent = app.next_actuation().await;
        assert_eq!(sent.service, "/vehicle_high_beam_tx");
        assert_eq!(sent.member, member);
        assert_eq!(sent.value, MwComValue::Bool(false));
        assert_eq!(
            broker
                .authorized_access(&ALLOW_ALL)
                .get_datapoint(signal_id)
                .await
                .unwrap()
                .value,
            DataValue::Bool(true)
        );
        app.inbound
            .send(MwComMessage {
                service: "/vehicle_high_beam_rx".into(),
                instance: "network_rx".into(),
                member: member.into(),
                value: MwComValue::Bool(false),
                source_timestamp: Some(SystemTime::now()),
                quality: SignalQuality::Valid,
            })
            .await
            .unwrap();
        wait_for_datapoint(&broker, signal_id, DataValue::Bool(false)).await;
    }
    shutdown_tx.send(()).unwrap();
    timeout(Duration::from_secs(1), task)
        .await
        .unwrap()
        .unwrap()
        .unwrap();
}
