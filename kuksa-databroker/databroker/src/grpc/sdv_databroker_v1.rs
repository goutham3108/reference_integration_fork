use std::{collections::HashMap, pin::Pin};

use databroker_proto::sdv::databroker::v1 as proto;
use futures::Stream;
use tonic::{Request, Response, Status};

use crate::{
    broker::{self, ActuationError, ReadError},
    permissions::Permissions,
    types::{DataType, DataValue, EntryType},
};

#[tonic::async_trait]
impl proto::broker_server::Broker for broker::DataBroker {
    async fn get_datapoints(
        &self,
        request: Request<proto::GetDatapointsRequest>,
    ) -> Result<Response<proto::GetDatapointsReply>, Status> {
        let permissions = request_permissions(&request)?;
        let request = request.into_inner();
        let access = self.authorized_access(&permissions);
        let mut datapoints = HashMap::new();

        for path in request.datapoints {
            let result = match access.get_datapoint_by_path(&path).await {
                Ok(datapoint) => to_proto_datapoint(datapoint),
                Err(ReadError::NotFound) => {
                    failed_datapoint(proto::datapoint::Failure::UnknownDatapoint)
                }
                Err(ReadError::PermissionDenied | ReadError::PermissionExpired) => {
                    failed_datapoint(proto::datapoint::Failure::AccessDenied)
                }
            };
            datapoints.insert(path, result);
        }

        Ok(Response::new(proto::GetDatapointsReply { datapoints }))
    }

    async fn set_datapoints(
        &self,
        request: Request<proto::SetDatapointsRequest>,
    ) -> Result<Response<proto::SetDatapointsReply>, Status> {
        let permissions = request_permissions(&request)?;
        let request = request.into_inner();
        let access = self.authorized_access(&permissions);
        let mut errors = HashMap::new();

        for (path, datapoint) in request.datapoints {
            let Some(value) = datapoint.value.and_then(from_proto_value) else {
                errors.insert(path, proto::DatapointError::InvalidType as i32);
                continue;
            };

            let Some(metadata) = access.get_metadata_by_path(&path).await else {
                errors.insert(path, proto::DatapointError::UnknownDatapoint as i32);
                continue;
            };
            if metadata.entry_type != EntryType::Actuator {
                errors.insert(path, proto::DatapointError::AccessDenied as i32);
                continue;
            }

            match access.actuate(&metadata.id, &value).await {
                Ok(()) => {}
                Err((error, _)) => {
                    errors.insert(path, map_actuation_error(error) as i32);
                }
            }
        }

        Ok(Response::new(proto::SetDatapointsReply { errors }))
    }

    type SubscribeStream =
        Pin<Box<dyn Stream<Item = Result<proto::SubscribeReply, Status>> + Send + 'static>>;

    async fn subscribe(
        &self,
        _request: Request<proto::SubscribeRequest>,
    ) -> Result<Response<Self::SubscribeStream>, Status> {
        Err(Status::unimplemented(
            "VDB query subscriptions are not implemented by this adapter",
        ))
    }

    async fn get_metadata(
        &self,
        request: Request<proto::GetMetadataRequest>,
    ) -> Result<Response<proto::GetMetadataReply>, Status> {
        let permissions = request_permissions(&request)?;
        let request = request.into_inner();
        let access = self.authorized_access(&permissions);
        let names = request.names;
        let list = if names.is_empty() {
            access
                .map_entries(|entry| to_proto_metadata(entry.metadata()))
                .await
        } else {
            let mut metadata = Vec::new();
            for name in names {
                if let Some(entry) = access.get_metadata_by_path(&name).await {
                    metadata.push(to_proto_metadata(&entry));
                }
            }
            metadata
        };

        Ok(Response::new(proto::GetMetadataReply { list }))
    }
}

fn request_permissions<T>(request: &Request<T>) -> Result<Permissions, Status> {
    let permissions = request
        .extensions()
        .get::<Permissions>()
        .ok_or_else(|| Status::unauthenticated("Unauthenticated"))?;
    Ok(permissions.clone())
}

fn failed_datapoint(failure: proto::datapoint::Failure) -> proto::Datapoint {
    proto::Datapoint {
        timestamp: None,
        value: Some(proto::datapoint::Value::FailureValue(failure as i32)),
    }
}

fn to_proto_datapoint(datapoint: broker::Datapoint) -> proto::Datapoint {
    let timestamp = Some(datapoint.ts.into());
    let value = match datapoint.value {
        DataValue::NotAvailable => {
            return failed_datapoint(proto::datapoint::Failure::NotAvailable)
        }
        DataValue::Bool(value) => proto::datapoint::Value::BoolValue(value),
        DataValue::String(value) => proto::datapoint::Value::StringValue(value),
        DataValue::Int32(value) => proto::datapoint::Value::Int32Value(value),
        DataValue::Int64(value) => proto::datapoint::Value::Int64Value(value),
        DataValue::Uint32(value) => proto::datapoint::Value::Uint32Value(value),
        DataValue::Uint64(value) => proto::datapoint::Value::Uint64Value(value),
        DataValue::Float(value) => proto::datapoint::Value::FloatValue(value),
        DataValue::Double(value) => proto::datapoint::Value::DoubleValue(value),
        DataValue::StringArray(values) => {
            proto::datapoint::Value::StringArray(proto::StringArray { values })
        }
        DataValue::BoolArray(values) => {
            proto::datapoint::Value::BoolArray(proto::BoolArray { values })
        }
        DataValue::Int32Array(values) => {
            proto::datapoint::Value::Int32Array(proto::Int32Array { values })
        }
        DataValue::Int64Array(values) => {
            proto::datapoint::Value::Int64Array(proto::Int64Array { values })
        }
        DataValue::Uint32Array(values) => {
            proto::datapoint::Value::Uint32Array(proto::Uint32Array { values })
        }
        DataValue::Uint64Array(values) => {
            proto::datapoint::Value::Uint64Array(proto::Uint64Array { values })
        }
        DataValue::FloatArray(values) => {
            proto::datapoint::Value::FloatArray(proto::FloatArray { values })
        }
        DataValue::DoubleArray(values) => {
            proto::datapoint::Value::DoubleArray(proto::DoubleArray { values })
        }
    };
    proto::Datapoint {
        timestamp,
        value: Some(value),
    }
}

fn from_proto_value(value: proto::datapoint::Value) -> Option<DataValue> {
    use proto::datapoint::Value;

    match value {
        Value::FailureValue(_) => None,
        Value::StringValue(value) => Some(DataValue::String(value)),
        Value::BoolValue(value) => Some(DataValue::Bool(value)),
        Value::Int32Value(value) => Some(DataValue::Int32(value)),
        Value::Int64Value(value) => Some(DataValue::Int64(value)),
        Value::Uint32Value(value) => Some(DataValue::Uint32(value)),
        Value::Uint64Value(value) => Some(DataValue::Uint64(value)),
        Value::FloatValue(value) => Some(DataValue::Float(value)),
        Value::DoubleValue(value) => Some(DataValue::Double(value)),
        Value::StringArray(value) => Some(DataValue::StringArray(value.values)),
        Value::BoolArray(value) => Some(DataValue::BoolArray(value.values)),
        Value::Int32Array(value) => Some(DataValue::Int32Array(value.values)),
        Value::Int64Array(value) => Some(DataValue::Int64Array(value.values)),
        Value::Uint32Array(value) => Some(DataValue::Uint32Array(value.values)),
        Value::Uint64Array(value) => Some(DataValue::Uint64Array(value.values)),
        Value::FloatArray(value) => Some(DataValue::FloatArray(value.values)),
        Value::DoubleArray(value) => Some(DataValue::DoubleArray(value.values)),
    }
}

fn map_actuation_error(error: ActuationError) -> proto::DatapointError {
    match error {
        ActuationError::NotFound => proto::DatapointError::UnknownDatapoint,
        ActuationError::WrongType | ActuationError::UnsupportedType => {
            proto::DatapointError::InvalidType
        }
        ActuationError::OutOfBounds => proto::DatapointError::OutOfBounds,
        ActuationError::PermissionDenied | ActuationError::PermissionExpired => {
            proto::DatapointError::AccessDenied
        }
        ActuationError::ProviderNotAvailable
        | ActuationError::ProviderAlreadyExists
        | ActuationError::TransmissionFailure => proto::DatapointError::InternalError,
    }
}

fn to_proto_metadata(metadata: &broker::Metadata) -> proto::Metadata {
    let data_type = match metadata.data_type {
        DataType::String => proto::DataType::String,
        DataType::Bool => proto::DataType::Bool,
        DataType::Int8 => proto::DataType::Int8,
        DataType::Int16 => proto::DataType::Int16,
        DataType::Int32 => proto::DataType::Int32,
        DataType::Int64 => proto::DataType::Int64,
        DataType::Uint8 => proto::DataType::Uint8,
        DataType::Uint16 => proto::DataType::Uint16,
        DataType::Uint32 => proto::DataType::Uint32,
        DataType::Uint64 => proto::DataType::Uint64,
        DataType::Float => proto::DataType::Float,
        DataType::Double => proto::DataType::Double,
        DataType::StringArray => proto::DataType::StringArray,
        DataType::BoolArray => proto::DataType::BoolArray,
        DataType::Int8Array => proto::DataType::Int8Array,
        DataType::Int16Array => proto::DataType::Int16Array,
        DataType::Int32Array => proto::DataType::Int32Array,
        DataType::Int64Array => proto::DataType::Int64Array,
        DataType::Uint8Array => proto::DataType::Uint8Array,
        DataType::Uint16Array => proto::DataType::Uint16Array,
        DataType::Uint32Array => proto::DataType::Uint32Array,
        DataType::Uint64Array => proto::DataType::Uint64Array,
        DataType::FloatArray => proto::DataType::FloatArray,
        DataType::DoubleArray => proto::DataType::DoubleArray,
    };
    let change_type = match metadata.change_type {
        broker::ChangeType::Static => proto::ChangeType::Static,
        broker::ChangeType::OnChange => proto::ChangeType::OnChange,
        broker::ChangeType::Continuous => proto::ChangeType::Continuous,
    };

    proto::Metadata {
        id: metadata.id,
        name: metadata.path.clone(),
        data_type: data_type as i32,
        change_type: change_type as i32,
        description: metadata.description.clone(),
    }
}

#[cfg(test)]
mod tests {
    use super::{from_proto_value, to_proto_datapoint};
    use crate::{broker::Datapoint, types::DataValue};
    use databroker_proto::sdv::databroker::v1 as proto;
    use std::time::SystemTime;

    #[test]
    fn vdb_boolean_datapoint_round_trips() {
        let value = from_proto_value(proto::datapoint::Value::BoolValue(true));
        assert_eq!(value, Some(DataValue::Bool(true)));

        let result = to_proto_datapoint(Datapoint {
            ts: SystemTime::UNIX_EPOCH,
            source_ts: None,
            value: DataValue::Bool(true),
        });
        assert!(matches!(
            result.value,
            Some(proto::datapoint::Value::BoolValue(true))
        ));
    }
}
