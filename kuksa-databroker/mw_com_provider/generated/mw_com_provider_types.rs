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

use score_com::{CommData, Reloc};
use std::default::Default;

pub mod vehicle {
    use super::*;

    #[repr(C)]
    #[derive(Debug, Clone, PartialEq, Default, Reloc, CommData)]
    #[comm_data(id = "BoolSample")]
    pub struct BoolSample {
        pub value: bool,
    }

    impl From<bool> for BoolSample {
        fn from(value: bool) -> Self {
            Self { value }
        }
    }

    #[repr(C)]
    #[derive(Debug, Clone, PartialEq, Default, Reloc, CommData)]
    #[comm_data(id = "U8Sample")]
    pub struct U8Sample {
        pub value: u8,
    }

    impl From<u8> for U8Sample {
        fn from(value: u8) -> Self {
            Self { value }
        }
    }

    #[repr(C)]
    #[derive(Debug, Clone, PartialEq, Default, Reloc, CommData)]
    #[comm_data(id = "F32Sample")]
    pub struct F32Sample {
        pub value: f32,
    }

    impl From<f32> for F32Sample {
        fn from(value: f32) -> Self {
            Self { value }
        }
    }

    #[repr(C)]
    #[derive(Debug, Clone, PartialEq, Default, Reloc, CommData)]
    #[comm_data(id = "String16Sample")]
    pub struct String16Sample {
        pub value: [u8; 16],
    }

    impl From<[u8; 16]> for String16Sample {
        fn from(value: [u8; 16]) -> Self {
            Self { value }
        }
    }

    #[cfg(test)]
    mod tests {
        use super::*;
        use std::mem::{align_of, size_of};

        #[test]
        fn primitive_samples_match_bcm_layouts() {
            assert_eq!((size_of::<BoolSample>(), align_of::<BoolSample>()), (1, 1));
            assert_eq!((size_of::<U8Sample>(), align_of::<U8Sample>()), (1, 1));
            assert_eq!((size_of::<F32Sample>(), align_of::<F32Sample>()), (4, 4));
            assert_eq!((size_of::<String16Sample>(), align_of::<String16Sample>()), (16, 1));
            assert!(BoolSample::from(true).value);
            assert_eq!(U8Sample::from(100).value, 100);
            assert_eq!(F32Sample::from(12.5).value, 12.5);
            assert_eq!(String16Sample::from(*b"0123456789ABCDEF").value, *b"0123456789ABCDEF");
        }
    }
}
