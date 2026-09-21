/********************************************************************************
 * Copyright (c) 2026 Contributors to the Eclipse Foundation
 *
 * See the NOTICE file(s) distributed with this work for additional
 * information regarding copyright ownership.
 *
 * This program and the accompanying materials are made available under the
 * terms of the Apache License 2.0 which is available at
 * https://www.apache.org/licenses/LICENSE-2.0
 *
 * SPDX-License-Identifier: Apache-2.0
 ********************************************************************************/

use score_com::{interface, CommData, ProviderInfo, Publisher, Reloc, Subscriber};

pub const VSS_MAX_PATH_LEN: usize = 160;
pub const VSS_MAX_VALUE_LEN: usize = 128;

// A generic carrier for any KUKSA VSS signal: path/value are UTF-8 text
// truncated to their buffer size, with *_len holding the actual byte length.
// This lets the producer forward any VSS path, not a fixed set.
#[derive(Debug, Reloc, CommData)]
#[repr(C)]
#[comm_data(id = "VssSignal")]
pub struct VssSignal {
    pub path: [u8; VSS_MAX_PATH_LEN],
    pub path_len: u16,
    pub value: [u8; VSS_MAX_VALUE_LEN],
    pub value_len: u16,
}

impl VssSignal {
    pub fn new(path: &str, value: &str) -> Self {
        let mut signal = VssSignal {
            path: [0u8; VSS_MAX_PATH_LEN],
            path_len: 0,
            value: [0u8; VSS_MAX_VALUE_LEN],
            value_len: 0,
        };
        signal.path_len = pack(path, &mut signal.path);
        signal.value_len = pack(value, &mut signal.value);
        signal
    }

    pub fn path_str(&self) -> String {
        unpack(&self.path, self.path_len)
    }

    pub fn value_str(&self) -> String {
        unpack(&self.value, self.value_len)
    }
}

fn pack<const N: usize>(text: &str, buf: &mut [u8; N]) -> u16 {
    let bytes = text.as_bytes();
    let len = bytes.len().min(N);
    buf[..len].copy_from_slice(&bytes[..len]);
    len as u16
}

fn unpack<const N: usize>(buf: &[u8; N], len: u16) -> String {
    let len = (len as usize).min(N);
    String::from_utf8_lossy(&buf[..len]).into_owned()
}

interface!(
    interface Vehicle {
        Id = "VehicleInterface",
        vss_signal: Event<VssSignal>,
    }
);
