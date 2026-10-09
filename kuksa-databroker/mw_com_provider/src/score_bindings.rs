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

use crate::config::ProviderConfig;
use crate::error::MwComProviderError;
use crate::generated;
use crate::transport::{MwComMessage, MwComTransport};
use async_trait::async_trait;
use std::collections::HashSet;

#[derive(Debug, Clone, Copy, Eq, PartialEq)]
pub struct ScoreBinding<'a> {
    pub service_name: &'a str,
    pub instance_name: &'a str,
    pub instance_specifier: &'a str,
    pub member_name: &'a str,
    pub element_kind: &'a str,
    pub payload_type: &'a str,
}

impl<'a> From<&'a generated::GenericMwComElement> for ScoreBinding<'a> {
    fn from(element: &'a generated::GenericMwComElement) -> Self {
        Self {
            service_name: element.service_name,
            instance_name: element.instance_name,
            instance_specifier: element.instance_specifier,
            member_name: element.member_name,
            element_kind: element.element_kind,
            payload_type: element.payload_type,
        }
    }
}

pub fn generated_score_bindings() -> impl Iterator<Item = ScoreBinding<'static>> {
    generated::GENERATED_GENERIC_MW_COM_ELEMENTS
        .iter()
        .map(ScoreBinding::from)
}

pub fn find_score_binding(
    service: &str,
    instance: &str,
    member: &str,
) -> Option<&'static generated::GenericMwComElement> {
    generated::GENERATED_GENERIC_MW_COM_ELEMENTS
        .iter()
        .find(|element| {
            element.service_name == service
                && (element.instance_name == instance || element.instance_specifier == instance)
                && element.member_name == member
        })
}

pub fn validate_score_bindings(config: &ProviderConfig) -> Result<(), MwComProviderError> {
    for mapping in &config.mappings {
        if let Some(binding) = &mapping.actuation_binding {
            if find_score_binding(&binding.service, &binding.instance, &binding.member).is_none() {
                return Err(MwComProviderError::Config(format!(
                    "missing actuation binding for {}",
                    mapping.vss_path
                )));
            }
        }
        let element = find_score_binding(&mapping.service, &mapping.instance, &mapping.member)
            .ok_or_else(|| {
                MwComProviderError::Config(format!(
                    "mapping {} references missing generated SCORE binding {}:{}:{}",
                    mapping.vss_path, mapping.service, mapping.instance, mapping.member
                ))
            })?;

        if element.instance_specifier.is_empty() {
            return Err(MwComProviderError::Config(format!(
                "mapping {} uses generated SCORE binding {}:{}:{} without an instance_specifier",
                mapping.vss_path, mapping.service, mapping.instance, mapping.member
            )));
        }
    }

    Ok(())
}

#[async_trait]
pub trait ScoreRuntimeAdapter: Send + Sync {
    async fn connect(&mut self) -> Result<(), MwComProviderError>;
    async fn disconnect(&mut self) -> Result<(), MwComProviderError>;

    async fn find_service(&self, binding: ScoreBinding<'_>) -> Result<bool, MwComProviderError>;

    async fn subscribe(&mut self, binding: ScoreBinding<'_>) -> Result<(), MwComProviderError>;

    async fn unsubscribe(&mut self, binding: ScoreBinding<'_>) -> Result<(), MwComProviderError>;

    async fn recv(&mut self) -> Result<Option<MwComMessage>, MwComProviderError>;

    async fn send_actuation(
        &mut self,
        binding: ScoreBinding<'_>,
        message: MwComMessage,
    ) -> Result<(), MwComProviderError>;
}

pub struct ScoreBindingTransport<A> {
    adapter: A,
    subscribed: HashSet<(&'static str, &'static str, &'static str)>,
}

impl<A> ScoreBindingTransport<A> {
    pub fn new(adapter: A) -> Self {
        Self {
            adapter,
            subscribed: HashSet::new(),
        }
    }

    pub fn adapter(&self) -> &A {
        &self.adapter
    }

    pub fn adapter_mut(&mut self) -> &mut A {
        &mut self.adapter
    }

    fn resolve(
        service: &str,
        instance: &str,
        member: &str,
    ) -> Result<&'static generated::GenericMwComElement, MwComProviderError> {
        find_score_binding(service, instance, member).ok_or_else(|| {
            MwComProviderError::Transport(format!(
                "no generated SCORE binding for {service}:{instance}:{member}"
            ))
        })
    }
}

#[async_trait]
impl<A> MwComTransport for ScoreBindingTransport<A>
where
    A: ScoreRuntimeAdapter,
{
    async fn connect(&mut self) -> Result<(), MwComProviderError> {
        self.adapter.connect().await
    }

    async fn disconnect(&mut self) -> Result<(), MwComProviderError> {
        let subscriptions = self.subscribed.drain().collect::<Vec<_>>();
        for (service, instance, member) in subscriptions {
            let binding = Self::resolve(service, instance, member)?;
            self.adapter.unsubscribe(binding.into()).await?;
        }
        self.adapter.disconnect().await
    }

    async fn subscribe(
        &mut self,
        service: &str,
        instance: &str,
        member: &str,
    ) -> Result<(), MwComProviderError> {
        let element = Self::resolve(service, instance, member)?;
        let binding = ScoreBinding::from(element);
        let key = (
            element.service_name,
            element.instance_name,
            element.member_name,
        );

        if self.subscribed.contains(&key) {
            return Err(MwComProviderError::Transport(format!(
                "already subscribed to {service}:{instance}:{member}"
            )));
        }

        if !self.adapter.find_service(binding).await? {
            return Err(MwComProviderError::Transport(format!(
                "SCORE service {} at {} is not available",
                binding.service_name, binding.instance_specifier
            )));
        }

        self.adapter.subscribe(binding).await?;
        self.subscribed.insert(key);
        Ok(())
    }

    async fn recv(&mut self) -> Result<MwComMessage, MwComProviderError> {
        let message = self
            .adapter
            .recv()
            .await?
            .ok_or(MwComProviderError::NoData)?;
        Ok(message)
    }

    async fn send_actuation(&mut self, message: MwComMessage) -> Result<(), MwComProviderError> {
        let element = Self::resolve(&message.service, &message.instance, &message.member)?;
        self.adapter
            .send_actuation(ScoreBinding::from(element), message)
            .await
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::config::{Direction, SignalMapping, VssDataType};
    use crate::quality::SignalQuality;
    use crate::transport::MwComValue;
    use std::sync::{Arc, Mutex};

    #[derive(Default)]
    struct RecordingAdapter {
        calls: Arc<Mutex<Vec<String>>>,
        next_message: Option<MwComMessage>,
    }

    #[async_trait]
    impl ScoreRuntimeAdapter for RecordingAdapter {
        async fn connect(&mut self) -> Result<(), MwComProviderError> {
            self.calls.lock().unwrap().push("connect".into());
            Ok(())
        }

        async fn disconnect(&mut self) -> Result<(), MwComProviderError> {
            self.calls.lock().unwrap().push("disconnect".into());
            Ok(())
        }

        async fn find_service(
            &self,
            binding: ScoreBinding<'_>,
        ) -> Result<bool, MwComProviderError> {
            self.calls
                .lock()
                .unwrap()
                .push(format!("find:{}", binding.instance_specifier));
            Ok(true)
        }

        async fn subscribe(&mut self, binding: ScoreBinding<'_>) -> Result<(), MwComProviderError> {
            self.calls
                .lock()
                .unwrap()
                .push(format!("subscribe:{}", binding.member_name));
            Ok(())
        }

        async fn unsubscribe(
            &mut self,
            binding: ScoreBinding<'_>,
        ) -> Result<(), MwComProviderError> {
            self.calls
                .lock()
                .unwrap()
                .push(format!("unsubscribe:{}", binding.member_name));
            Ok(())
        }

        async fn recv(&mut self) -> Result<Option<MwComMessage>, MwComProviderError> {
            Ok(self.next_message.take())
        }

        async fn send_actuation(
            &mut self,
            binding: ScoreBinding<'_>,
            _message: MwComMessage,
        ) -> Result<(), MwComProviderError> {
            self.calls
                .lock()
                .unwrap()
                .push(format!("send:{}", binding.member_name));
            Ok(())
        }
    }

    fn provider_config() -> ProviderConfig {
        ProviderConfig {
            provider_name: "score".into(),
            reconnect: Default::default(),
            queue_capacity: 4,
            stale_after_ms: 1_000,
            mappings: vec![SignalMapping {
                signal_id: 42,
                vss_path: "Vehicle.Speed".into(),
                datatype: VssDataType::Double,
                service: "VehicleDynamicsService".into(),
                instance: "front_vehicle".into(),
                member: "speed".into(),
                actuation_binding: None,
                field: None,
                unit: Some("km/h".into()),
                scale: 1.0,
                offset: 0.0,
                min: None,
                max: None,
                required_quality: SignalQuality::Valid,
                direction: Direction::Datapoint,
                cycle_time_ms: 100,
            }],
        }
    }

    #[test]
    fn resolves_generated_binding_by_provider_instance_or_score_specifier() {
        let by_provider =
            find_score_binding("VehicleDynamicsService", "front_vehicle", "speed").unwrap();
        let by_score = find_score_binding(
            "VehicleDynamicsService",
            "/Vehicle/Service2/Instance",
            "speed",
        )
        .unwrap();

        assert_eq!(by_provider, by_score);
        assert_eq!(by_provider.instance_specifier, "/Vehicle/Service2/Instance");
    }

    #[test]
    fn resolves_high_beam_signal_to_gateway_receive_instance() {
        let binding =
            find_score_binding("/vehicle_high_beam_rx", "network_rx", "high_beam_state").unwrap();

        assert_eq!(binding.instance_specifier, "/vehicle_high_beam/network_rx");
        assert_eq!(binding.payload_type, "HighBeamState");
    }

    #[test]
    fn generated_provider_config_includes_high_beam_datapoint() {
        let config = ProviderConfig::load_json("generated/mw_com_provider_config.json").unwrap();
        validate_score_bindings(&config).unwrap();

        let mapping = config
            .mappings
            .iter()
            .find(|mapping| mapping.vss_path == "Vehicle.Body.Lights.Beam.High.IsOn")
            .unwrap();
        assert_eq!(mapping.signal_id, 45);
        assert_eq!(mapping.datatype, crate::config::VssDataType::Bool);
        assert_eq!(mapping.service, "/vehicle_high_beam_rx");
        assert_eq!(mapping.instance, "network_rx");
        assert_eq!(mapping.member, "high_beam_state");
        assert_eq!(mapping.direction, crate::config::Direction::Bidirectional);
        let high_tx = mapping.actuation_binding.as_ref().unwrap();
        assert_eq!(high_tx.member, "high_beam_state");
        let output = config
            .mappings
            .iter()
            .find(|mapping| mapping.vss_path == "Vehicle.Body.Lights.Beam.Low.IsOn")
            .unwrap();
        assert_eq!(output.signal_id, 46);
        assert_eq!(output.datatype, crate::config::VssDataType::Bool);
        assert_eq!(output.direction, crate::config::Direction::Bidirectional);
        assert_eq!(output.service, "/vehicle_high_beam_rx");
        assert_eq!(output.member, "low_beam_state");
        let low_tx = output.actuation_binding.as_ref().unwrap();
        assert_eq!(low_tx.member, "low_beam_state");
        let element = find_score_binding(&low_tx.service, &low_tx.instance, &low_tx.member).unwrap();
        assert_eq!(element.instance_specifier, "/vehicle_high_beam/local_tx");
        assert_eq!(element.sample_size, 32);
        assert_eq!(element.sample_alignment, 16);
    }

    #[test]
    fn validates_provider_config_against_generated_score_bindings() {
        validate_score_bindings(&provider_config()).unwrap();
    }

    #[tokio::test]
    async fn transport_delegates_to_runtime_adapter_with_generated_binding() {
        let calls = Arc::new(Mutex::new(Vec::new()));
        let adapter = RecordingAdapter {
            calls: Arc::clone(&calls),
            next_message: Some(MwComMessage {
                service: "VehicleDynamicsService".into(),
                instance: "front_vehicle".into(),
                member: "speed".into(),
                value: MwComValue::F64(12.5),
                source_timestamp: None,
                quality: SignalQuality::Valid,
            }),
        };
        let mut transport = ScoreBindingTransport::new(adapter);

        transport.connect().await.unwrap();
        transport
            .subscribe("VehicleDynamicsService", "front_vehicle", "speed")
            .await
            .unwrap();
        assert_eq!(transport.recv().await.unwrap().value, MwComValue::F64(12.5));
        transport
            .send_actuation(MwComMessage {
                service: "VehicleDynamicsService".into(),
                instance: "front_vehicle".into(),
                member: "target_speed".into(),
                value: MwComValue::F64(80.0),
                source_timestamp: None,
                quality: SignalQuality::Valid,
            })
            .await
            .unwrap();
        transport.disconnect().await.unwrap();

        assert_eq!(
            calls.lock().unwrap().as_slice(),
            [
                "connect",
                "find:/Vehicle/Service2/Instance",
                "subscribe:speed",
                "send:target_speed",
                "unsubscribe:speed",
                "disconnect",
            ]
        );
    }
}
