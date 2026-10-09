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
use crate::config::{Direction, SignalMapping, VssDataType};
use crate::error::MwComProviderError;
use crate::mapper::MwComMapper;
use crate::transport::MwComTransport;
use crate::transport::{MwComMessage, MwComValue};
use async_trait::async_trait;
use databroker::broker::{
    ActuationChange, ActuationError, ActuationProvider, DataBroker, DataType, EntryType,
    GetValuesProviderResponse, Metadata, RegisterSignalError, SignalProvider,
};
use databroker::permissions::Permissions;
use databroker::types::{SignalId, TimeInterval};
use std::collections::HashMap;
use std::path::Path;
use std::sync::Arc;
use tokio::sync::{mpsc, oneshot, RwLock};
use tokio::time::sleep;
use tracing::{debug, info, warn};

#[derive(Clone)]
pub struct MwComProvider {
    broker: DataBroker,
    permissions: Permissions,
    transport: Arc<RwLock<dyn MwComTransport>>,
    mapper: Arc<MwComMapper>,
}

impl MwComProvider {
    pub fn new<T>(
        broker: DataBroker,
        permissions: Permissions,
        config: ProviderConfig,
        transport: T,
    ) -> Result<Self, MwComProviderError>
    where
        T: MwComTransport + 'static,
    {
        Ok(Self {
            broker,
            permissions,
            transport: Arc::new(RwLock::new(transport)),
            mapper: Arc::new(MwComMapper::new(config)?),
        })
    }

    pub fn from_config_file<T>(
        broker: DataBroker,
        permissions: Permissions,
        config_path: impl AsRef<Path>,
        transport: T,
    ) -> Result<Self, MwComProviderError>
    where
        T: MwComTransport + 'static,
    {
        let config = ProviderConfig::load_json(config_path)?;
        Self::new(broker, permissions, config, transport)
    }

    pub async fn register_with_broker(&self) -> Result<(), MwComProviderError> {
        let broker = self.broker.authorized_access(&self.permissions);
        validate_mappings_against_broker(&self.mapper, &broker).await?;

        let signal_intervals = self.mapper.signal_intervals();
        let signal_count = signal_intervals.len();

        if signal_count > 0 {
            broker
                .register_signals(signal_intervals, Box::new(self.clone()))
                .await
                .map_err(|error| MwComProviderError::Registration(error.1))?;
        }

        let actuator_signal_ids = self.mapper.actuator_signal_ids();
        if !actuator_signal_ids.is_empty() {
            broker
                .provide_actuation(actuator_signal_ids, Box::new(self.clone()))
                .await
                .map_err(|error| MwComProviderError::Registration(error.1))?;
        }

        info!(
            provider = %self.mapper.config().provider_name,
            signals = signal_count,
            actuators = self.mapper.actuator_signal_ids().len(),
            "mw::com provider registered with Databroker"
        );
        Ok(())
    }

    pub async fn connect_and_subscribe(&self) -> Result<(), MwComProviderError> {
        let mut transport = self.transport.write().await;
        transport.connect().await?;
        for mapping in self.mapper.subscriptions() {
            transport
                .subscribe(&mapping.service, &mapping.instance, &mapping.member)
                .await?;
        }
        Ok(())
    }

    pub async fn shutdown(&self) -> Result<(), MwComProviderError> {
        self.transport.write().await.disconnect().await
    }

    pub async fn run_until_shutdown(
        &self,
        mut shutdown: oneshot::Receiver<()>,
    ) -> Result<(), MwComProviderError> {
        let mut reconnect_delay = self.mapper.config().reconnect.initial_delay();

        loop {
            match self.connect_and_subscribe().await {
                Ok(()) => {
                    reconnect_delay = self.mapper.config().reconnect.initial_delay();
                    info!(provider = %self.mapper.config().provider_name, "mw::com provider connected");
                }
                Err(error) => {
                    warn!(%error, ?reconnect_delay, "mw::com provider connect failed; retrying");
                    if let Err(shutdown_error) = self.shutdown().await {
                        warn!(%shutdown_error, "mw::com provider cleanup after connect failure failed");
                    }
                    tokio::select! {
                        _ = sleep(reconnect_delay) => {
                            reconnect_delay = self.mapper.config().reconnect.next_delay(reconnect_delay);
                            continue;
                        }
                        _ = &mut shutdown => {
                            self.shutdown().await?;
                            return Ok(());
                        }
                    }
                }
            }

            loop {
                tokio::select! {
                    result = self.recv_and_publish_one() => {
                        match result {
                            Ok(()) => {}
                            Err(MwComProviderError::Quality(error)) | Err(MwComProviderError::Mapping(error)) => {
                                warn!(%error, "mw::com sample rejected");
                            }
                            Err(MwComProviderError::NoData) => {
                                tokio::task::yield_now().await;
                            }
                            Err(MwComProviderError::Shutdown) => {
                                info!("mw::com transport shut down");
                                self.shutdown().await?;
                                return Ok(());
                            }
                            Err(error) => {
                                warn!(%error, ?reconnect_delay, "mw::com receive failed; reconnecting");
                                let _ = self.shutdown().await;
                                break;
                            }
                        }
                    }
                    _ = &mut shutdown => {
                        self.shutdown().await?;
                        return Ok(());
                    }
                }
            }

            sleep(reconnect_delay).await;
            reconnect_delay = self.mapper.config().reconnect.next_delay(reconnect_delay);
        }
    }

    async fn recv_and_publish_one(&self) -> Result<(), MwComProviderError> {
        let message = self.transport.write().await.recv().await?;
        let (signal_id, update) = self.mapper.message_to_update(&message)?;
        let broker = self.broker.authorized_access(&self.permissions);
        broker
            .update_entries(vec![(signal_id, update)])
            .await
            .map_err(|errors| MwComProviderError::BrokerUpdate(format!("{errors:?}")))?;
        debug!(signal_id, "mw::com sample written to Databroker");
        Ok(())
    }
}

pub struct MwComProviderWorker<T>
where
    T: MwComTransport,
{
    broker: DataBroker,
    permissions: Permissions,
    transport: T,
    mapper: Arc<MwComMapper>,
    actuation_tx: mpsc::Sender<MwComMessage>,
    actuation_rx: mpsc::Receiver<MwComMessage>,
}

impl<T> MwComProviderWorker<T>
where
    T: MwComTransport + 'static,
{
    pub fn new(
        broker: DataBroker,
        permissions: Permissions,
        config: ProviderConfig,
        transport: T,
    ) -> Result<Self, MwComProviderError> {
        let queue_capacity = config.queue_capacity;
        let mapper = Arc::new(MwComMapper::new(config)?);
        let (actuation_tx, actuation_rx) = mpsc::channel(queue_capacity);
        Ok(Self {
            broker,
            permissions,
            transport,
            mapper,
            actuation_tx,
            actuation_rx,
        })
    }

    pub async fn register_with_broker(&self) -> Result<(), MwComProviderError> {
        let broker = self.broker.authorized_access(&self.permissions);
        validate_mappings_against_broker(&self.mapper, &broker).await?;

        let signal_intervals = self.mapper.signal_intervals();
        let signal_count = signal_intervals.len();
        if signal_count > 0 {
            broker
                .register_signals(
                    signal_intervals,
                    Box::new(QueuedSignalProvider {
                        mapper: Arc::clone(&self.mapper),
                    }),
                )
                .await
                .map_err(|error| MwComProviderError::Registration(error.1))?;
        }

        let actuator_signal_ids = self.mapper.actuator_signal_ids();
        let actuator_count = actuator_signal_ids.len();
        if !actuator_signal_ids.is_empty() {
            broker
                .provide_actuation(
                    actuator_signal_ids,
                    Box::new(QueuedActuationProvider {
                        mapper: Arc::clone(&self.mapper),
                        actuation_tx: self.actuation_tx.clone(),
                    }),
                )
                .await
                .map_err(|error| MwComProviderError::Registration(error.1))?;
        }

        info!(
            provider = %self.mapper.config().provider_name,
            signals = signal_count,
            actuators = actuator_count,
            "mw::com provider worker registered with Databroker"
        );
        Ok(())
    }

    async fn connect_and_subscribe(&mut self) -> Result<(), MwComProviderError> {
        self.transport.connect().await?;
        for mapping in self.mapper.subscriptions() {
            self.transport
                .subscribe(&mapping.service, &mapping.instance, &mapping.member)
                .await?;
        }
        Ok(())
    }

    pub async fn shutdown(&mut self) -> Result<(), MwComProviderError> {
        self.transport.disconnect().await
    }

    pub async fn run_until_shutdown(
        mut self,
        mut shutdown: oneshot::Receiver<()>,
    ) -> Result<(), MwComProviderError> {
        let mut reconnect_delay = self.mapper.config().reconnect.initial_delay();

        loop {
            match self.connect_and_subscribe().await {
                Ok(()) => {
                    reconnect_delay = self.mapper.config().reconnect.initial_delay();
                    info!(provider = %self.mapper.config().provider_name, "mw::com provider worker connected");
                }
                Err(error) => {
                    warn!(%error, ?reconnect_delay, "mw::com provider worker connect failed; retrying");
                    tokio::select! {
                        _ = sleep(reconnect_delay) => {
                            reconnect_delay = self.mapper.config().reconnect.next_delay(reconnect_delay);
                            continue;
                        }
                        _ = &mut shutdown => {
                            self.shutdown().await?;
                            return Ok(());
                        }
                    }
                }
            }

            loop {
                self.drain_actuation_queue().await?;
                tokio::select! {
                    result = self.transport.recv() => {
                        let result = match result {
                            Ok(message) => self.publish_message(message).await,
                            Err(error) => Err(error),
                        };
                        match result {
                            Ok(()) => {}
                            Err(MwComProviderError::Quality(error)) | Err(MwComProviderError::Mapping(error)) => {
                                warn!(%error, "mw::com sample rejected");
                            }
                            Err(MwComProviderError::NoData) => {
                                tokio::task::yield_now().await;
                            }
                            Err(MwComProviderError::Shutdown) => {
                                info!("mw::com transport shut down");
                                self.shutdown().await?;
                                return Ok(());
                            }
                            Err(error) => {
                                warn!(%error, ?reconnect_delay, "mw::com receive failed; reconnecting");
                                let _ = self.shutdown().await;
                                break;
                            }
                        }
                    }
                    Some(message) = self.actuation_rx.recv() => {
                        let service = message.service.clone();
                        let value = message.value.clone();
                        self.transport.send_actuation(message).await?;
                        info!(%service, ?value, "Command transmitted through mw::com Tx");
                    }
                    _ = &mut shutdown => {
                        self.shutdown().await?;
                        return Ok(());
                    }
                }
            }

            sleep(reconnect_delay).await;
            reconnect_delay = self.mapper.config().reconnect.next_delay(reconnect_delay);
        }
    }

    async fn drain_actuation_queue(&mut self) -> Result<(), MwComProviderError> {
        while let Ok(message) = self.actuation_rx.try_recv() {
            let service = message.service.clone();
            let value = message.value.clone();
            self.transport.send_actuation(message).await?;
            info!(%service, ?value, "Command transmitted through mw::com Tx");
        }
        Ok(())
    }

    async fn publish_message(&self, message: MwComMessage) -> Result<(), MwComProviderError> {
        let value = message.value.clone();
        let (signal_id, update) = self.mapper.message_to_update(&message)?;
        let broker = self.broker.authorized_access(&self.permissions);
        broker
            .update_entries(vec![(signal_id, update)])
            .await
            .map_err(|errors| MwComProviderError::BrokerUpdate(format!("{errors:?}")))?;
        info!(
            signal_id,
            ?value,
            "Remote input received through mw::com Rx and written to Databroker"
        );
        Ok(())
    }
}

struct QueuedSignalProvider {
    mapper: Arc<MwComMapper>,
}

#[async_trait]
impl SignalProvider for QueuedSignalProvider {
    async fn update_filter(
        &self,
        update_filters: HashMap<SignalId, Option<TimeInterval>>,
    ) -> Result<(), (RegisterSignalError, String)> {
        debug!(
            provider = %self.mapper.config().provider_name,
            filters = update_filters.len(),
            "mw::com provider worker received Databroker filter update"
        );
        Ok(())
    }

    fn is_available(&self) -> bool {
        true
    }

    async fn get_signals_values_from_provider(
        &mut self,
        _signals_ids: Vec<SignalId>,
    ) -> Result<GetValuesProviderResponse, ()> {
        Err(())
    }
}

struct QueuedActuationProvider {
    mapper: Arc<MwComMapper>,
    actuation_tx: mpsc::Sender<MwComMessage>,
}

#[async_trait]
impl ActuationProvider for QueuedActuationProvider {
    async fn actuate(
        &self,
        actuation_changes: Vec<ActuationChange>,
    ) -> Result<(), (ActuationError, String)> {
        for change in actuation_changes {
            let message = self
                .mapper
                .actuation_to_message(&change)
                .map_err(|error| (ActuationError::WrongType, error.to_string()))?;
            self.actuation_tx.send(message).await.map_err(|error| {
                (
                    ActuationError::TransmissionFailure,
                    format!("mw::com actuation worker is not available: {error}"),
                )
            })?;
            info!(signal_id = change.id, value = ?change.data_value, "KUKSA actuator command queued for mw::com Tx");
        }
        Ok(())
    }

    fn is_available(&self) -> bool {
        !self.actuation_tx.is_closed()
    }
}

async fn validate_mappings_against_broker(
    mapper: &MwComMapper,
    broker: &databroker::broker::AuthorizedAccess<'_, '_>,
) -> Result<(), MwComProviderError> {
    for mapping in &mapper.config().mappings {
        let metadata = broker
            .get_metadata_by_path(&mapping.vss_path)
            .await
            .ok_or_else(|| {
                MwComProviderError::Registration(format!(
                    "mapping for {} references a VSS path that is not registered in Databroker",
                    mapping.vss_path
                ))
            })?;

        validate_mapping_metadata(mapping, &metadata)?;
    }

    Ok(())
}

fn validate_mapping_metadata(
    mapping: &SignalMapping,
    metadata: &Metadata,
) -> Result<(), MwComProviderError> {
    if metadata.id != mapping.signal_id {
        return Err(MwComProviderError::Registration(format!(
            "mapping for {} uses signal id {}, but Databroker registered id {}",
            mapping.vss_path, mapping.signal_id, metadata.id
        )));
    }

    if !datatype_matches(mapping.datatype, &metadata.data_type) {
        return Err(MwComProviderError::Registration(format!(
            "mapping for {} uses datatype {:?}, but Databroker registered {:?}",
            mapping.vss_path, mapping.datatype, metadata.data_type
        )));
    }

    if !direction_matches(mapping.direction, &metadata.entry_type) {
        return Err(MwComProviderError::Registration(format!(
            "mapping for {} uses direction {:?}, but Databroker registered entry type {:?}",
            mapping.vss_path, mapping.direction, metadata.entry_type
        )));
    }

    Ok(())
}

fn datatype_matches(mapping_type: VssDataType, broker_type: &DataType) -> bool {
    matches!(
        (mapping_type, broker_type),
        (VssDataType::Bool, DataType::Bool)
            | (VssDataType::String, DataType::String)
            | (VssDataType::Int8, DataType::Int8)
            | (VssDataType::Int32, DataType::Int32)
            | (VssDataType::Int64, DataType::Int64)
            | (VssDataType::Uint8, DataType::Uint8)
            | (VssDataType::Uint32, DataType::Uint32)
            | (VssDataType::Uint64, DataType::Uint64)
            | (VssDataType::Float, DataType::Float)
            | (VssDataType::Double, DataType::Double)
    )
}

fn direction_matches(direction: Direction, entry_type: &EntryType) -> bool {
    match direction {
        Direction::Datapoint => matches!(entry_type, EntryType::Sensor | EntryType::Actuator),
        Direction::Actuator | Direction::Bidirectional => matches!(entry_type, EntryType::Actuator),
    }
}

#[async_trait]
impl SignalProvider for MwComProvider {
    async fn update_filter(
        &self,
        update_filters: HashMap<SignalId, Option<TimeInterval>>,
    ) -> Result<(), (RegisterSignalError, String)> {
        debug!(
            filters = update_filters.len(),
            "mw::com provider received Databroker filter update"
        );
        Ok(())
    }

    fn is_available(&self) -> bool {
        true
    }

    async fn get_signals_values_from_provider(
        &mut self,
        _signals_ids: Vec<SignalId>,
    ) -> Result<GetValuesProviderResponse, ()> {
        Err(())
    }
}

#[async_trait]
impl ActuationProvider for MwComProvider {
    async fn actuate(
        &self,
        actuation_changes: Vec<ActuationChange>,
    ) -> Result<(), (ActuationError, String)> {
        for change in actuation_changes {
            let message = self
                .mapper
                .actuation_to_message(&change)
                .map_err(|error| (ActuationError::WrongType, error.to_string()))?;
            self.transport
                .write()
                .await
                .send_actuation(message)
                .await
                .map_err(|error| (ActuationError::TransmissionFailure, error.to_string()))?;
        }
        Ok(())
    }

    fn is_available(&self) -> bool {
        true
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::quality::SignalQuality;
    use crate::transport::mock::MockMwComTransport;
    use databroker::broker::ChangeType;
    use databroker::permissions::ALLOW_ALL;
    use tokio::sync::mpsc;

    fn mapping(direction: Direction, datatype: VssDataType) -> SignalMapping {
        SignalMapping {
            signal_id: 42,
            vss_path: "Vehicle.Speed".into(),
            datatype,
            service: "VehicleDynamicsService".into(),
            instance: "front_vehicle".into(),
            member: "speed".into(),
            actuation_binding: None,
            field: None,
            unit: Some("km/h".into()),
            scale: 1.0,
            offset: 0.0,
            min: Some(0.0),
            max: Some(300.0),
            required_quality: SignalQuality::Valid,
            direction,
            cycle_time_ms: 100,
        }
    }

    fn metadata(entry_type: EntryType, data_type: DataType) -> Metadata {
        Metadata {
            id: 42,
            path: "Vehicle.Speed".into(),
            glob_path: "Vehicle/Speed".into(),
            data_type,
            entry_type,
            change_type: ChangeType::Continuous,
            description: "Vehicle speed.".into(),
            min: None,
            max: None,
            allowed: None,
            unit: Some("km/h".into()),
        }
    }

    fn config(mapping: SignalMapping) -> ProviderConfig {
        ProviderConfig {
            provider_name: "test".into(),
            reconnect: Default::default(),
            queue_capacity: 4,
            stale_after_ms: 1_000,
            mappings: vec![mapping],
        }
    }

    fn mock_transport() -> MockMwComTransport {
        let (_inbound_tx, inbound_rx) = mpsc::channel(1);
        let (outbound_tx, _outbound_rx) = mpsc::channel(1);
        MockMwComTransport::new(inbound_rx, outbound_tx)
    }

    async fn broker_with_entry(entry_type: EntryType, data_type: DataType) -> (DataBroker, i32) {
        let broker = DataBroker::new("test", "test");
        let id = broker
            .authorized_access(&ALLOW_ALL)
            .add_entry(
                "Vehicle.Speed".into(),
                data_type,
                ChangeType::Continuous,
                entry_type,
                "Vehicle speed.".into(),
                None,
                None,
                None,
                Some("km/h".into()),
            )
            .await
            .unwrap();

        (broker, id)
    }

    #[test]
    fn accepts_matching_sensor_datapoint_mapping() {
        let mapping = mapping(Direction::Datapoint, VssDataType::Double);
        let metadata = metadata(EntryType::Sensor, DataType::Double);

        validate_mapping_metadata(&mapping, &metadata).unwrap();
    }

    #[test]
    fn rejects_signal_id_mismatch() {
        let mapping = mapping(Direction::Datapoint, VssDataType::Double);
        let mut metadata = metadata(EntryType::Sensor, DataType::Double);
        metadata.id = 7;

        let error = validate_mapping_metadata(&mapping, &metadata).unwrap_err();
        assert!(error.to_string().contains("uses signal id 42"));
    }

    #[test]
    fn rejects_datatype_mismatch() {
        let mapping = mapping(Direction::Datapoint, VssDataType::Double);
        let metadata = metadata(EntryType::Sensor, DataType::Float);

        let error = validate_mapping_metadata(&mapping, &metadata).unwrap_err();
        assert!(error.to_string().contains("uses datatype Double"));
    }

    #[test]
    fn rejects_actuator_mapping_for_sensor_entry() {
        let mapping = mapping(Direction::Actuator, VssDataType::Double);
        let metadata = metadata(EntryType::Sensor, DataType::Double);

        let error = validate_mapping_metadata(&mapping, &metadata).unwrap_err();
        assert!(error.to_string().contains("uses direction Actuator"));
    }

    #[test]
    fn accepts_bidirectional_mapping_for_actuator_entry() {
        let mapping = mapping(Direction::Bidirectional, VssDataType::Double);
        let metadata = metadata(EntryType::Actuator, DataType::Double);

        validate_mapping_metadata(&mapping, &metadata).unwrap();
    }

    #[test]
    fn rejects_datapoint_mapping_for_attribute_entry() {
        let mapping = mapping(Direction::Datapoint, VssDataType::Double);
        let metadata = metadata(EntryType::Attribute, DataType::Double);

        let error = validate_mapping_metadata(&mapping, &metadata).unwrap_err();

        assert!(error.to_string().contains("entry type Attribute"));
    }

    #[test]
    fn accepts_all_supported_scalar_datatype_pairs() {
        let cases = [
            (VssDataType::Bool, DataType::Bool),
            (VssDataType::String, DataType::String),
            (VssDataType::Int8, DataType::Int8),
            (VssDataType::Int32, DataType::Int32),
            (VssDataType::Int64, DataType::Int64),
            (VssDataType::Uint8, DataType::Uint8),
            (VssDataType::Uint32, DataType::Uint32),
            (VssDataType::Uint64, DataType::Uint64),
            (VssDataType::Float, DataType::Float),
            (VssDataType::Double, DataType::Double),
        ];

        for (mapping_type, broker_type) in cases {
            assert!(datatype_matches(mapping_type, &broker_type));
        }
    }

    #[tokio::test]
    async fn register_with_broker_accepts_matching_databroker_metadata() {
        let (broker, signal_id) = broker_with_entry(EntryType::Sensor, DataType::Double).await;
        let mut mapping = mapping(Direction::Datapoint, VssDataType::Double);
        mapping.signal_id = signal_id;
        let provider =
            MwComProvider::new(broker, ALLOW_ALL.clone(), config(mapping), mock_transport())
                .unwrap();

        provider.register_with_broker().await.unwrap();
    }

    #[tokio::test]
    async fn register_with_broker_rejects_missing_databroker_path() {
        let broker = DataBroker::new("test", "test");
        let provider = MwComProvider::new(
            broker,
            ALLOW_ALL.clone(),
            config(mapping(Direction::Datapoint, VssDataType::Double)),
            mock_transport(),
        )
        .unwrap();

        let error = provider.register_with_broker().await.unwrap_err();

        assert!(error
            .to_string()
            .contains("references a VSS path that is not registered"));
    }

    #[tokio::test]
    async fn register_with_broker_rejects_databroker_datatype_mismatch() {
        let (broker, signal_id) = broker_with_entry(EntryType::Sensor, DataType::Float).await;
        let mut mapping = mapping(Direction::Datapoint, VssDataType::Double);
        mapping.signal_id = signal_id;
        let provider =
            MwComProvider::new(broker, ALLOW_ALL.clone(), config(mapping), mock_transport())
                .unwrap();

        let error = provider.register_with_broker().await.unwrap_err();

        assert!(error.to_string().contains("uses datatype Double"));
    }
}
