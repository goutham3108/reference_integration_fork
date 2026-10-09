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

use crate::error::MwComProviderError;
use crate::quality::SignalQuality;
use crate::score_bindings::{ScoreBinding, ScoreRuntimeAdapter};
use crate::transport::{MwComMessage, MwComValue};
use async_trait::async_trait;
use score_com::{
    Builder, FindServiceSpecifier, InstanceSpecifier, Interface, LolaRuntimeBuilderImpl,
    LolaRuntimeImpl, OfferedProducer, Producer, Publisher, Runtime, RuntimeBuilder,
    SampleContainer, ServiceDiscovery, Subscriber, Subscription,
};
use std::path::{Path, PathBuf};
use std::time::SystemTime;

type LolaRuntime = LolaRuntimeImpl;

type VehicleDynamicsServiceInterfaceAlias =
    crate::mw_com_provider_interfaces::vehicle::VehicleDynamicsServiceInterface;
type VehicleDynamicsServiceProducer =
    <VehicleDynamicsServiceInterfaceAlias as Interface>::Producer<LolaRuntime>;
type VehicleDynamicsServiceOfferedProducer =
    <VehicleDynamicsServiceProducer as Producer<LolaRuntime>>::OfferedProducer;
type VehicleDynamicsServiceSpeedSubscription = <<LolaRuntime as Runtime>::Subscriber<
    crate::mw_com_provider_types::vehicle::SpeedSample,
> as Subscriber<
    crate::mw_com_provider_types::vehicle::SpeedSample,
    LolaRuntime,
>>::Subscription;
type VehicleDynamicsServiceTargetSpeedSubscription = <<LolaRuntime as Runtime>::Subscriber<
    crate::mw_com_provider_types::vehicle::TargetSpeed,
> as Subscriber<
    crate::mw_com_provider_types::vehicle::TargetSpeed,
    LolaRuntime,
>>::Subscription;
type VehicleHighBeamRxInterfaceAlias =
    crate::mw_com_provider_interfaces::high_beam::VehicleHighBeamRxInterface;
type VehicleHighBeamRxHighBeamState = crate::mw_com_provider_types::high_beam::HighBeamState;
type VehicleHighBeamRxHighBeamStateSubscription = <<LolaRuntime as Runtime>::Subscriber<VehicleHighBeamRxHighBeamState> as Subscriber<
    VehicleHighBeamRxHighBeamState,
    LolaRuntime,
>>::Subscription;

pub struct LolaScoreRuntimeAdapter {
    high_beam_tx: Option<crate::high_beam_tx::TxOfferedProducer>,
    config_path: PathBuf,
    runtime: Option<LolaRuntime>,
    vehicledynamicsservice_speed_subscription: Option<VehicleDynamicsServiceSpeedSubscription>,
    vehicledynamicsservice_target_speed_subscription:
        Option<VehicleDynamicsServiceTargetSpeedSubscription>,
    vehiclehighbeamrx_high_beam_state_subscription:
        Option<VehicleHighBeamRxHighBeamStateSubscription>,
    vehiclehighbeamrx_low_beam_state_subscription:
        Option<VehicleHighBeamRxHighBeamStateSubscription>,
    vehicledynamicsservice_offered_producer: Option<VehicleDynamicsServiceOfferedProducer>,
    vehicledynamicsservice_producer_instance_specifier: Option<String>,
}

// SAFETY: The adapter does not expose references to the native LoLa handles it owns, and provider
// access to the transport is serialized through mutable operations on the surrounding lock.
unsafe impl Sync for LolaScoreRuntimeAdapter {}

impl LolaScoreRuntimeAdapter {
    pub fn new(config_path: impl Into<PathBuf>) -> Self {
        let config_path = config_path.into();
        Self {
            high_beam_tx: None,
            config_path,
            runtime: None,
            vehicledynamicsservice_speed_subscription: None,
            vehicledynamicsservice_target_speed_subscription: None,
            vehiclehighbeamrx_high_beam_state_subscription: None,
            vehiclehighbeamrx_low_beam_state_subscription: None,
            vehicledynamicsservice_offered_producer: None,
            vehicledynamicsservice_producer_instance_specifier: None,
        }
    }

    pub fn from_score_config_env() -> Result<Self, MwComProviderError> {
        let config_path = std::env::var_os("SCORE_CONFIG_PATH").ok_or_else(|| {
            MwComProviderError::Config("SCORE_CONFIG_PATH must point to the LoLa config".into())
        })?;
        Ok(Self::new(PathBuf::from(config_path)))
    }

    pub fn config_path(&self) -> &Path {
        &self.config_path
    }

    fn runtime(&self) -> Result<&LolaRuntime, MwComProviderError> {
        self.runtime.as_ref().ok_or_else(|| {
            MwComProviderError::Transport("SCORE LoLa runtime is not connected".into())
        })
    }

    fn validate_binding(binding: ScoreBinding<'_>) -> Result<(), MwComProviderError> {
        match binding.service_name {
            "VehicleDynamicsService" => Ok(()),
            "/vehicle_high_beam_rx" => Ok(()),
            other => Err(MwComProviderError::Transport(format!(
                "LolaScoreRuntimeAdapter is not generated for SCORE service {other}"
            ))),
        }
    }

    fn instance_specifier(
        binding: ScoreBinding<'_>,
    ) -> Result<InstanceSpecifier, MwComProviderError> {
        InstanceSpecifier::new(binding.instance_specifier).map_err(|error| {
            MwComProviderError::Transport(format!(
                "invalid SCORE instance specifier {}: {error:?}",
                binding.instance_specifier
            ))
        })
    }

    fn score_error(context: &str, error: impl std::fmt::Debug) -> MwComProviderError {
        MwComProviderError::Transport(format!("{context}: {error:?}"))
    }

    fn ensure_vehicledynamicsservice_offered_producer(
        &mut self,
        binding: ScoreBinding<'_>,
    ) -> Result<&VehicleDynamicsServiceOfferedProducer, MwComProviderError> {
        if binding.service_name != "VehicleDynamicsService" {
            return Err(MwComProviderError::Transport(format!(
                "VehicleDynamicsService producer cannot publish {}",
                binding.service_name
            )));
        }

        if self.vehicledynamicsservice_offered_producer.is_none() {
            let specifier = Self::instance_specifier(binding)?;
            let producer = self
                .runtime()?
                .producer_builder::<VehicleDynamicsServiceInterfaceAlias>(specifier)
                .build()
                .map_err(|error| Self::score_error("SCORE producer build failed", error))?;
            let offered = producer
                .offer()
                .map_err(|error| Self::score_error("SCORE producer offer failed", error))?;
            self.vehicledynamicsservice_offered_producer = Some(offered);
            self.vehicledynamicsservice_producer_instance_specifier =
                Some(binding.instance_specifier.to_string());
        }

        if self
            .vehicledynamicsservice_producer_instance_specifier
            .as_deref()
            != Some(binding.instance_specifier)
        {
            return Err(MwComProviderError::Transport(format!(
                "SCORE producer is already offered for {}, cannot publish {}",
                self.vehicledynamicsservice_producer_instance_specifier
                    .as_deref()
                    .unwrap_or("<unknown>"),
                binding.instance_specifier
            )));
        }

        self.vehicledynamicsservice_offered_producer
            .as_ref()
            .ok_or_else(|| MwComProviderError::Transport("SCORE producer was not offered".into()))
    }
}

#[async_trait]
impl ScoreRuntimeAdapter for LolaScoreRuntimeAdapter {
    async fn connect(&mut self) -> Result<(), MwComProviderError> {
        let mut builder = LolaRuntimeBuilderImpl::new();
        builder.load_config(&self.config_path);
        let runtime = builder
            .build()
            .map_err(|error| Self::score_error("SCORE LoLa runtime build failed", error))?;
        if std::env::var("KUKSA_HIGH_BEAM_ACTUATION").as_deref() != Ok("0")
            && crate::high_beam_tx::configured(&self.config_path)? {
            self.high_beam_tx = Some(crate::high_beam_tx::offer(&runtime)?);
        }
        self.runtime = Some(runtime);
        Ok(())
    }

    async fn disconnect(&mut self) -> Result<(), MwComProviderError> {
        if let Some(producer) = self.high_beam_tx.take() {
            producer.unoffer().map_err(|error| Self::score_error("high-beam Tx unoffer failed", error))?;
        }
        if let Some(subscription) = self.vehicledynamicsservice_speed_subscription.take() {
            let _ = subscription.unsubscribe();
        }
        if let Some(subscription) = self.vehicledynamicsservice_target_speed_subscription.take() {
            let _ = subscription.unsubscribe();
        }
        if let Some(subscription) = self.vehiclehighbeamrx_high_beam_state_subscription.take() {
            let _ = subscription.unsubscribe();
        }
        if let Some(subscription) = self.vehiclehighbeamrx_low_beam_state_subscription.take() {
            let _ = subscription.unsubscribe();
        }
        if let Some(producer) = self.vehicledynamicsservice_offered_producer.take() {
            producer
                .unoffer()
                .map_err(|error| Self::score_error("SCORE producer unoffer failed", error))?;
        }
        self.vehicledynamicsservice_producer_instance_specifier = None;
        self.runtime = None;
        Ok(())
    }

    async fn find_service(&self, binding: ScoreBinding<'_>) -> Result<bool, MwComProviderError> {
        Self::validate_binding(binding)?;
        match binding.service_name {
            "VehicleDynamicsService" => {
                let discovery = self
                    .runtime()?
                    .find_service::<VehicleDynamicsServiceInterfaceAlias>(
                        FindServiceSpecifier::Specific(Self::instance_specifier(binding)?),
                    );
                let instances = discovery
                    .get_available_instances()
                    .map_err(|error| Self::score_error("SCORE service discovery failed", error))?;
                Ok(instances.into_iter().next().is_some())
            }
            "/vehicle_high_beam_rx" => {
                let discovery = self.runtime()?.find_service::<VehicleHighBeamRxInterfaceAlias>(
                    FindServiceSpecifier::Specific(Self::instance_specifier(binding)?),
                );
                let instances = discovery
                    .get_available_instances()
                    .map_err(|error| Self::score_error("SCORE service discovery failed", error))?;
                Ok(instances.into_iter().next().is_some())
            }
            other => Err(MwComProviderError::Transport(format!(
                "LolaScoreRuntimeAdapter is not generated for SCORE service {other}"
            ))),
        }
    }

    async fn subscribe(&mut self, binding: ScoreBinding<'_>) -> Result<(), MwComProviderError> {
        Self::validate_binding(binding)?;
        match (binding.service_name, binding.member_name) {
            ("VehicleDynamicsService", "speed") => {
                if self.vehicledynamicsservice_speed_subscription.is_some() {
                    return Ok(());
                }
                let discovery = self
                    .runtime()?
                    .find_service::<VehicleDynamicsServiceInterfaceAlias>(
                        FindServiceSpecifier::Specific(Self::instance_specifier(binding)?),
                    );
                let consumer_builder = discovery
                    .get_available_instances()
                    .map_err(|error| Self::score_error("SCORE service discovery failed", error))?
                    .into_iter()
                    .next()
                    .ok_or_else(|| {
                        MwComProviderError::Transport(format!(
                            "SCORE service {} at {} is not available",
                            binding.service_name, binding.instance_specifier
                        ))
                    })?;
                let consumer = consumer_builder
                    .build()
                    .map_err(|error| Self::score_error("SCORE consumer build failed", error))?;
                self.vehicledynamicsservice_speed_subscription =
                    Some(consumer.speed.subscribe(3).map_err(|error| {
                        Self::score_error("SCORE speed subscribe failed", error)
                    })?);
                Ok(())
            }
            ("VehicleDynamicsService", "target_speed") => {
                if self
                    .vehicledynamicsservice_target_speed_subscription
                    .is_some()
                {
                    return Ok(());
                }
                let discovery = self
                    .runtime()?
                    .find_service::<VehicleDynamicsServiceInterfaceAlias>(
                        FindServiceSpecifier::Specific(Self::instance_specifier(binding)?),
                    );
                let consumer_builder = discovery
                    .get_available_instances()
                    .map_err(|error| Self::score_error("SCORE service discovery failed", error))?
                    .into_iter()
                    .next()
                    .ok_or_else(|| {
                        MwComProviderError::Transport(format!(
                            "SCORE service {} at {} is not available",
                            binding.service_name, binding.instance_specifier
                        ))
                    })?;
                let consumer = consumer_builder
                    .build()
                    .map_err(|error| Self::score_error("SCORE consumer build failed", error))?;
                self.vehicledynamicsservice_target_speed_subscription =
                    Some(consumer.target_speed.subscribe(3).map_err(|error| {
                        Self::score_error("SCORE target_speed subscribe failed", error)
                    })?);
                Ok(())
            }
            ("/vehicle_high_beam_rx", "high_beam_state") => {
                if self.vehiclehighbeamrx_high_beam_state_subscription.is_some() {
                    return Ok(());
                }
                let discovery = self.runtime()?.find_service::<VehicleHighBeamRxInterfaceAlias>(
                    FindServiceSpecifier::Specific(Self::instance_specifier(binding)?),
                );
                let consumer_builder = discovery
                    .get_available_instances()
                    .map_err(|error| Self::score_error("SCORE service discovery failed", error))?
                    .into_iter()
                    .next()
                    .ok_or_else(|| {
                        MwComProviderError::Transport(format!(
                            "SCORE service {} at {} is not available",
                            binding.service_name, binding.instance_specifier
                        ))
                    })?;
                let consumer = consumer_builder
                    .build()
                    .map_err(|error| Self::score_error("SCORE consumer build failed", error))?;
                self.vehiclehighbeamrx_high_beam_state_subscription = Some(
                    consumer
                        .high_beam_state
                        .subscribe(3)
                        .map_err(|error| Self::score_error("SCORE high_beam_state subscribe failed", error))?,
                );
                Ok(())
            }
            ("/vehicle_high_beam_rx", "low_beam_state") => {
                if self.vehiclehighbeamrx_low_beam_state_subscription.is_some() {
                    return Ok(());
                }
                let discovery = self.runtime()?.find_service::<VehicleHighBeamRxInterfaceAlias>(
                    FindServiceSpecifier::Specific(Self::instance_specifier(binding)?),
                );
                let consumer_builder = discovery
                    .get_available_instances()
                    .map_err(|error| Self::score_error("SCORE service discovery failed", error))?
                    .into_iter()
                    .next()
                    .ok_or_else(|| MwComProviderError::Transport("lighting Rx service is not available".into()))?;
                let consumer = consumer_builder
                    .build()
                    .map_err(|error| Self::score_error("SCORE consumer build failed", error))?;
                self.vehiclehighbeamrx_low_beam_state_subscription = Some(
                    consumer.low_beam_state.subscribe(3)
                        .map_err(|error| Self::score_error("SCORE low_beam_state subscribe failed", error))?,
                );
                Ok(())
            }
            _ => Ok(()),
        }
    }

    async fn unsubscribe(&mut self, binding: ScoreBinding<'_>) -> Result<(), MwComProviderError> {
        Self::validate_binding(binding)?;
        match (binding.service_name, binding.member_name) {
            ("VehicleDynamicsService", "speed") => {
                if let Some(subscription) = self.vehicledynamicsservice_speed_subscription.take() {
                    let _ = subscription.unsubscribe();
                }
                Ok(())
            }
            ("VehicleDynamicsService", "target_speed") => {
                if let Some(subscription) =
                    self.vehicledynamicsservice_target_speed_subscription.take()
                {
                    let _ = subscription.unsubscribe();
                }
                Ok(())
            }
            ("/vehicle_high_beam_rx", "high_beam_state") => {
                if let Some(subscription) = self.vehiclehighbeamrx_high_beam_state_subscription.take() {
                    let _ = subscription.unsubscribe();
                }
                Ok(())
            }
            ("/vehicle_high_beam_rx", "low_beam_state") => {
                if let Some(subscription) = self.vehiclehighbeamrx_low_beam_state_subscription.take() {
                    let _ = subscription.unsubscribe();
                }
                Ok(())
            }
            _ => Ok(()),
        }
    }

    async fn recv(&mut self) -> Result<Option<MwComMessage>, MwComProviderError> {
        if let Some(subscription) = self.vehicledynamicsservice_speed_subscription.as_ref() {
            let mut samples = SampleContainer::new(3);
            let count = subscription
                .try_receive(&mut samples, 1)
                .map_err(|error| Self::score_error("SCORE speed receive failed", error))?;
            if count > 0 {
                let sample = samples.pop_front().ok_or_else(|| {
                    MwComProviderError::Transport("SCORE speed receive returned no sample".into())
                })?;
                return Ok(Some(MwComMessage {
                    service: "VehicleDynamicsService".into(),
                    instance: "front_vehicle".into(),
                    member: "speed".into(),
                    value: MwComValue::F64(sample.value),
                    source_timestamp: Some(SystemTime::now()),
                    quality: score_quality(sample.quality)?,
                }));
            }
        }
        if let Some(subscription) = self
            .vehicledynamicsservice_target_speed_subscription
            .as_ref()
        {
            let mut samples = SampleContainer::new(3);
            let count = subscription
                .try_receive(&mut samples, 1)
                .map_err(|error| Self::score_error("SCORE target_speed receive failed", error))?;
            if count > 0 {
                let sample = samples.pop_front().ok_or_else(|| {
                    MwComProviderError::Transport(
                        "SCORE target_speed receive returned no sample".into(),
                    )
                })?;
                return Ok(Some(MwComMessage {
                    service: "VehicleDynamicsService".into(),
                    instance: "front_vehicle".into(),
                    member: "target_speed".into(),
                    value: MwComValue::F64(sample.value),
                    source_timestamp: Some(SystemTime::now()),
                    quality: SignalQuality::Valid,
                }));
            }
        }
        if let Some(subscription) = self.vehiclehighbeamrx_high_beam_state_subscription.as_ref() {
            let mut samples = SampleContainer::new(3);
            let count = subscription
                .try_receive(&mut samples, 1)
                .map_err(|error| Self::score_error("SCORE high_beam_state receive failed", error))?;
            if count > 0 {
                let sample = samples.pop_front().ok_or_else(|| {
                    MwComProviderError::Transport(
                        "SCORE high_beam_state receive returned no sample".into(),
                    )
                })?;
                return Ok(Some(MwComMessage {
                    service: "/vehicle_high_beam_rx".into(),
                    instance: "network_rx".into(),
                    member: "high_beam_state".into(),
                    value: MwComValue::Bool(sample.value),
                    source_timestamp: Some(SystemTime::now()),
                    quality: SignalQuality::Valid,
                }));
            }
        }
        if let Some(subscription) = self.vehiclehighbeamrx_low_beam_state_subscription.as_ref() {
            let mut samples = SampleContainer::new(3);
            let count = subscription
                .try_receive(&mut samples, 1)
                .map_err(|error| Self::score_error("SCORE low_beam_state receive failed", error))?;
            if count > 0 {
                let sample = samples.pop_front().ok_or_else(|| {
                    MwComProviderError::Transport("SCORE low_beam_state receive returned no sample".into())
                })?;
                return Ok(Some(MwComMessage {
                    service: "/vehicle_high_beam_rx".into(),
                    instance: "network_rx".into(),
                    member: "low_beam_state".into(),
                    value: MwComValue::Bool(sample.value),
                    source_timestamp: Some(SystemTime::now()),
                    quality: SignalQuality::Valid,
                }));
            }
        }
        Ok(None)
    }

    async fn send_actuation(
        &mut self,
        binding: ScoreBinding<'_>,
        message: MwComMessage,
    ) -> Result<(), MwComProviderError> {
        match (binding.service_name, binding.member_name) {
            ("/vehicle_high_beam_tx", "high_beam_state" | "low_beam_state") => {
                let value = bool_value(&message.value, binding)?;
                let producer = self.high_beam_tx.as_ref().ok_or_else(||
                    MwComProviderError::Transport("high-beam Tx actuation is disabled".into()))?;
                crate::high_beam_tx::send(producer, binding.member_name, value)
            }
            ("VehicleDynamicsService", "target_speed") => {
                let value = numeric_value(&message.value, binding).map(|value| value as f64)?;
                let producer = self.ensure_vehicledynamicsservice_offered_producer(binding)?;
                producer
                    .target_speed
                    .send(crate::mw_com_provider_types::vehicle::TargetSpeed { value: value })
                    .map_err(|error| Self::score_error("SCORE target_speed publish failed", error))
            }
            ("VehicleDynamicsService", "cruise_control_enabled") => {
                let value = bool_value(&message.value, binding)?;
                let producer = self.ensure_vehicledynamicsservice_offered_producer(binding)?;
                producer
                    .cruise_control_enabled
                    .send(
                        crate::mw_com_provider_types::vehicle::CruiseControlEnabled {
                            value: value,
                        },
                    )
                    .map_err(|error| {
                        Self::score_error("SCORE cruise_control_enabled publish failed", error)
                    })
            }
            (_, other) => Err(MwComProviderError::Transport(format!(
                "SCORE actuation is not generated for {}:{}",
                binding.service_name, other
            ))),
        }
    }
}

fn score_quality(value: u8) -> Result<SignalQuality, MwComProviderError> {
    match value {
        0 => Ok(SignalQuality::Invalid),
        1 => Ok(SignalQuality::Stale),
        2 => Ok(SignalQuality::Degraded),
        3 => Ok(SignalQuality::Valid),
        other => Err(MwComProviderError::Transport(format!(
            "unsupported SCORE quality value {other}"
        ))),
    }
}

fn numeric_value(value: &MwComValue, binding: ScoreBinding<'_>) -> Result<f64, MwComProviderError> {
    match value {
        MwComValue::F64(value) => Ok(*value),
        MwComValue::I64(value) => Ok(*value as f64),
        MwComValue::U64(value) => Ok(*value as f64),
        other => Err(MwComProviderError::Transport(format!(
            "{}:{} requires numeric actuation, got {other:?}",
            binding.service_name, binding.member_name
        ))),
    }
}

fn bool_value(value: &MwComValue, binding: ScoreBinding<'_>) -> Result<bool, MwComProviderError> {
    match value {
        MwComValue::Bool(value) => Ok(*value),
        other => Err(MwComProviderError::Transport(format!(
            "{}:{} requires bool actuation, got {other:?}",
            binding.service_name, binding.member_name
        ))),
    }
}
