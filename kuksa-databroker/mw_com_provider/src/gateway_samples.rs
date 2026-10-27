use crate::error::MwComProviderError;
use crate::transport::MwComValue;
#[cfg(feature = "score-lola")]
use score_com::{CommData, Reloc};

#[repr(C)]
#[derive(Debug, Clone, Default)]
#[cfg_attr(feature = "score-lola", derive(score_com::Reloc, score_com::CommData))]
#[cfg_attr(feature = "score-lola", comm_data(id = "HighBeamState"))]
pub struct HighBeamState {
    pub value: bool,
}

#[repr(C, align(16))]
#[derive(Debug, Clone, Default)]
#[cfg_attr(feature = "score-lola", derive(score_com::Reloc, score_com::CommData))]
#[cfg_attr(feature = "score-lola", comm_data(id = "HighBeamCommand"))]
pub struct HighBeamCommand {
    pub size: usize,
    pub padding: [u8; 8],
    pub data: [u8; 16],
}

#[repr(C, align(16))]
#[derive(Debug, Clone, Default)]
#[cfg_attr(feature = "score-lola", derive(score_com::Reloc, score_com::CommData))]
#[cfg_attr(feature = "score-lola", comm_data(id = "BodySignalText"))]
pub struct BodySignalText {
    pub size: usize,
    pub padding: [u8; 8],
    pub data: [u8; 32],
}

#[repr(C)]
#[derive(Debug, Clone, Default)]
#[cfg_attr(feature = "score-lola", derive(score_com::Reloc, score_com::CommData))]
#[cfg_attr(feature = "score-lola", comm_data(id = "SpeedSample"))]
pub struct SpeedSample {
    pub value: f64,
    pub quality: u8,
}

#[repr(C)]
#[derive(Debug, Clone, Default)]
#[cfg_attr(feature = "score-lola", derive(score_com::Reloc, score_com::CommData))]
#[cfg_attr(feature = "score-lola", comm_data(id = "SpeedAck"))]
pub struct SpeedAck {
    pub value: f64,
    pub quality: u8,
}

fn invalid(message: &str) -> MwComProviderError {
    MwComProviderError::Transport(message.into())
}

impl HighBeamCommand {
    pub fn encode(value: &MwComValue, datatype: &str) -> Result<Self, MwComProviderError> {
        let byte =
            match (datatype, value) {
                ("boolean", MwComValue::Bool(value)) => u8::from(*value),
                ("uint8", MwComValue::U64(value)) => u8::try_from(*value)
                    .map_err(|_| invalid("gateway uint8 target is out of range"))?,
                ("uint8", MwComValue::I64(value)) => u8::try_from(*value)
                    .map_err(|_| invalid("gateway uint8 target is out of range"))?,
                _ => return Err(invalid("gateway target datatype does not match the event")),
            };
        let mut sample = Self {
            size: 1,
            ..Self::default()
        };
        sample.data[0] = byte;
        Ok(sample)
    }

    pub fn decode(&self) -> Result<MwComValue, MwComProviderError> {
        if self.size != 1 {
            return Err(invalid(
                "gateway uint8 sample must contain exactly one byte",
            ));
        }
        Ok(MwComValue::U64(u64::from(self.data[0])))
    }
}

impl BodySignalText {
    pub fn encode(value: &MwComValue, datatype: &str) -> Result<Self, MwComProviderError> {
        let MwComValue::String(value) = value else {
            return Err(invalid("gateway text target requires a string"));
        };
        if datatype != "string" || value.len() > 32 {
            return Err(invalid("gateway text target exceeds 32 UTF-8 bytes"));
        }
        let mut sample = Self {
            size: value.len(),
            ..Self::default()
        };
        sample.data[..value.len()].copy_from_slice(value.as_bytes());
        Ok(sample)
    }

    pub fn decode(&self) -> Result<MwComValue, MwComProviderError> {
        let bytes = self
            .data
            .get(..self.size)
            .ok_or_else(|| invalid("gateway text sample exceeds its buffer"))?;
        let text = std::str::from_utf8(bytes)
            .map_err(|_| invalid("gateway text sample is not valid UTF-8"))?;
        Ok(MwComValue::String(text.into()))
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::mem::{align_of, offset_of, size_of};

    #[test]
    fn layouts_match_existing_gateway_and_cpp_types() {
        assert_eq!(
            (size_of::<HighBeamState>(), align_of::<HighBeamState>()),
            (1, 1)
        );
        assert_eq!(
            (size_of::<HighBeamCommand>(), align_of::<HighBeamCommand>()),
            (32, 16)
        );
        assert_eq!(offset_of!(HighBeamCommand, data), 16);
        assert_eq!(
            (size_of::<BodySignalText>(), align_of::<BodySignalText>()),
            (48, 16)
        );
        assert_eq!(offset_of!(BodySignalText, data), 16);
        assert_eq!(
            (size_of::<SpeedSample>(), offset_of!(SpeedSample, quality)),
            (16, 8)
        );
    }

    #[test]
    fn boolean_and_uint8_targets_have_no_native_layout_on_wire() {
        for value in [false, true] {
            let sample = HighBeamCommand::encode(&MwComValue::Bool(value), "boolean").unwrap();
            assert_eq!(sample.size, 1);
            assert_eq!(sample.data[0], u8::from(value));
            assert_eq!(sample.padding, [0; 8]);
        }
        let sample = HighBeamCommand::encode(&MwComValue::U64(100), "uint8").unwrap();
        assert_eq!(sample.decode().unwrap(), MwComValue::U64(100));
        assert!(HighBeamCommand::encode(&MwComValue::U64(256), "uint8").is_err());
        assert!(HighBeamCommand::encode(&MwComValue::I64(-1), "uint8").is_err());
        assert!(HighBeamCommand::encode(&MwComValue::Bool(true), "uint8").is_err());
    }

    #[test]
    fn text_round_trip_and_invalid_payloads() {
        for text in ["OFF", "FAST", "0123456789ABCDEF0123456789ABCDEF"] {
            let value = MwComValue::String(text.into());
            let sample = BodySignalText::encode(&value, "string").unwrap();
            assert_eq!(sample.size, text.len());
            assert_eq!(sample.decode().unwrap(), value);
        }
        assert!(BodySignalText::encode(&MwComValue::String("x".repeat(33)), "string").is_err());
        let bad_length = BodySignalText {
            size: 33,
            ..Default::default()
        };
        assert!(bad_length.decode().is_err());
        let mut bad_utf8 = BodySignalText {
            size: 1,
            ..Default::default()
        };
        bad_utf8.data[0] = 255;
        assert!(bad_utf8.decode().is_err());
        assert!(
            HighBeamCommand {
                size: 0,
                ..Default::default()
            }
            .decode()
            .is_err()
        );
    }
}
