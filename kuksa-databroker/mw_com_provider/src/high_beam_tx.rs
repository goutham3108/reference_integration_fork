use crate::error::MwComProviderError;
use score_com::{
    Builder, CommData, InstanceSpecifier, Interface, LolaRuntimeImpl, Producer, ProviderInfo,
    Publisher, Reloc, Runtime, Subscriber,
};

#[repr(C, align(16))]
#[derive(Debug, Clone, Default, Reloc, CommData)]
#[comm_data(id = "HighBeamCommand")]
pub struct HighBeamCommand {
    pub size: usize,
    pub padding: [u8; 8],
    pub data: [u8; 16],
}

const _: () = assert!(std::mem::size_of::<HighBeamCommand>() == 32);
const _: () = assert!(std::mem::align_of::<HighBeamCommand>() == 16);
const _: () = assert!(std::mem::offset_of!(HighBeamCommand, data) == 16);

score_com::interface!(interface HighBeamTx {
    Id = "HighBeamTx",
    high_beam_state: Event<HighBeamCommand>,
    low_beam_state: Event<HighBeamCommand>,
});

type TxProducer = <HighBeamTxInterface as Interface>::Producer<LolaRuntimeImpl>;
pub type TxOfferedProducer = <TxProducer as Producer<LolaRuntimeImpl>>::OfferedProducer;

pub fn offer(runtime: &LolaRuntimeImpl) -> Result<TxOfferedProducer, MwComProviderError> {
    let instance = InstanceSpecifier::new("/vehicle_high_beam/local_tx").map_err(|error| {
        MwComProviderError::Transport(format!("invalid high-beam Tx instance: {error:?}"))
    })?;
    runtime
        .producer_builder::<HighBeamTxInterface>(instance)
        .build()
        .map_err(|error| {
            MwComProviderError::Transport(format!("high-beam Tx build failed: {error:?}"))
        })?
        .offer()
        .map_err(|error| {
            MwComProviderError::Transport(format!("high-beam Tx offer failed: {error:?}"))
        })
}

pub fn send(
    producer: &TxOfferedProducer,
    member: &str,
    value: bool,
) -> Result<(), MwComProviderError> {
    let sample = command(value);
    let result = match member {
        "high_beam_state" => producer.high_beam_state.send(sample),
        "low_beam_state" => producer.low_beam_state.send(sample),
        other => {
            return Err(MwComProviderError::Transport(format!(
                "unknown lighting Tx event {other}"
            )))
        }
    };
    result.map_err(|error| {
        MwComProviderError::Transport(format!("lighting Tx {member} send failed: {error:?}"))
    })
}

fn command(value: bool) -> HighBeamCommand {
    let mut sample = HighBeamCommand {
        size: 1,
        ..Default::default()
    };
    sample.data[0] = u8::from(value);
    sample
}

pub fn configured(path: &std::path::Path) -> Result<bool, MwComProviderError> {
    let contents = std::fs::read_to_string(path)
        .map_err(|error| MwComProviderError::Config(error.to_string()))?;
    let manifest: serde_json::Value = serde_json::from_str(&contents)
        .map_err(|error| MwComProviderError::Config(error.to_string()))?;
    Ok(manifest
        .get("serviceInstances")
        .and_then(serde_json::Value::as_array)
        .is_some_and(|instances| {
            instances.iter().any(|instance| {
                instance
                    .get("instanceSpecifier")
                    .and_then(serde_json::Value::as_str)
                    == Some("/vehicle_high_beam/local_tx")
            })
        }))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn high_beam_tx_instance_is_valid_for_rust_runtime() {
        assert!(InstanceSpecifier::new("/vehicle_high_beam/local_tx").is_ok());
        assert!(InstanceSpecifier::new("vehicle_high_beam/local_tx").is_err());
    }

    #[test]
    fn command_matches_gateway_serialized_layout() {
        assert_eq!(std::mem::size_of::<HighBeamCommand>(), 32);
        assert_eq!(std::mem::align_of::<HighBeamCommand>(), 16);
        assert_eq!(std::mem::offset_of!(HighBeamCommand, data), 16);
        for value in [false, true] {
            let sample = command(value);
            assert_eq!(sample.size, 1);
            assert_eq!(sample.data[0], u8::from(value));
            assert_eq!(sample.padding, [0; 8]);
        }
    }
}
